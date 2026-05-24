"""
Phase 2 — Video scraping.

Scrapes ONLY the top competitors from channels.yaml.
Incremental: existing cached videos are kept; only new videos are fetched in full.
Stats (views/likes/comments) are refreshed on all cached videos each run.
All videos are stored so median calculation stays accurate for Phase 3.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from utils.config import Config, load_config, load_channels, write_channels
from utils.youtube_api import (
    build_client, get_channel_metadata, list_playlist_items,
    get_video_details, refresh_video_stats, QuotaExhaustedError,
)
from utils.cache import (
    load_video_cache, write_video_cache,
    load_channel_meta, write_channel_meta,
    mark_phase_complete, generate_run_id,
)

_RAW_VIDEOS_DIR = Path(__file__).parent.parent / "output" / "raw" / "videos"
_TRANSCRIPTS_DIR = Path(__file__).parent.parent / "output" / "raw" / "transcripts"


def _clear_transcripts() -> None:
    """Delete all transcript files so this run fetches fresh ones."""
    if _TRANSCRIPTS_DIR.exists():
        for f in _TRANSCRIPTS_DIR.glob("*.txt"):
            f.unlink()
    _TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    print("  [Phase 2] Transcript cache cleared — fresh transcripts will be fetched in Phase 3.")


def _scrape_channel(
    yt,
    channel_id: str,
    max_videos: int,
    max_age_months: int,
    min_duration: int,
) -> list[dict]:
    """
    Incremental scrape of one channel.

    - Loads existing cache for this channel.
    - Fetches current playlist; stops walking when it hits an already-cached video ID.
    - Full-fetches any video IDs not yet in cache.
    - Refreshes stats (views/likes/comments) on all cached videos — 1 quota unit each.
    - Drops videos older than max_age_months.
    - Returns merged list.
    """
    cutoff = datetime.now() - timedelta(days=max_age_months * 30)

    # Load existing cache
    existing_cache = load_video_cache(channel_id) or {}
    cached_videos: list[dict] = existing_cache.get("videos", [])
    cached_ids: set[str] = {v["id"] for v in cached_videos}

    # Ensure uploads playlist ID is available
    meta = load_channel_meta(channel_id) or {}
    if not meta.get("uploads_playlist_id"):
        channel_metas = get_channel_metadata(yt, [channel_id])
        if not channel_metas:
            return cached_videos
        m = channel_metas[0]
        meta = {
            "id": m.id, "title": m.title,
            "subs": m.subscriber_count, "views": m.view_count,
            "uploads_playlist_id": m.uploads_playlist_id,
        }
        write_channel_meta(channel_id, meta)

    playlist_id = meta.get("uploads_playlist_id", "")
    if not playlist_id:
        return cached_videos

    # Walk playlist; stop when we hit a video we already have
    current_ids = list_playlist_items(
        yt, playlist_id, stop_at_ids=cached_ids, max_items=max_videos
    )

    new_ids = [vid_id for vid_id in current_ids if vid_id not in cached_ids]

    # Full-fetch new videos
    new_videos: list[dict] = []
    if new_ids:
        all_details = get_video_details(yt, new_ids)
        for d in all_details:
            if d.duration_seconds < min_duration:
                continue
            try:
                pub = datetime.fromisoformat(d.published_at.replace("Z", "+00:00")).replace(tzinfo=None)
                if pub < cutoff:
                    continue
            except (ValueError, AttributeError):
                pass
            new_videos.append({
                "id": d.id,
                "title": d.title,
                "published_at": d.published_at,
                "duration_seconds": d.duration_seconds,
                "view_count": d.view_count,
                "like_count": d.like_count,
                "comment_count": d.comment_count,
                "description": d.description,
                "tags": d.tags,
                "thumbnail_url": d.thumbnail_url,
                "scraped_at": datetime.now().isoformat(),
            })

    # Refresh stats on all previously-cached videos (1 quota unit each)
    if cached_ids:
        refreshed = refresh_video_stats(yt, list(cached_ids))
        now = datetime.now().isoformat()
        for v in cached_videos:
            stats = refreshed.get(v["id"])
            if stats:
                v["view_count"] = stats.view_count
                v["like_count"] = stats.like_count
                v["comment_count"] = stats.comment_count
                v["stats_refreshed_at"] = now

    # Drop videos older than cutoff from cache
    merged: list[dict] = []
    for v in cached_videos + new_videos:
        try:
            pub = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            if pub >= cutoff:
                merged.append(v)
        except (ValueError, AttributeError, KeyError):
            merged.append(v)

    return merged


def run(cfg: Config, run_id: str | None = None, upstream=None) -> None:
    """
    Incremental scrape of all top competitors.
    Existing cached videos are preserved; only new videos are fetched in full.
    Stats are refreshed on all cached videos each run.
    """
    run_id = run_id or generate_run_id()
    channels_data = load_channels()

    top_competitors = channels_data.top_competitors or []
    if not top_competitors:
        print("[Phase 2] No top competitors found. Run Phase 1.5 first.")
        return

    # Wipe all transcript files — Phase 3 will re-fetch fresh ones for this run's candidates
    _clear_transcripts()

    yt = build_client(cfg.youtube_api_key)
    today = datetime.now().strftime("%Y-%m-%d")

    depth = cfg.settings.get("scrape_depth", {}).get("primary", {})
    max_videos = depth.get("max_videos", 100)
    max_age_months = depth.get("max_age_months", 24)
    min_duration = cfg.settings.get("video_filters", {}).get("min_duration_seconds", 60)
    min_views = cfg.settings.get("video_filters", {}).get("min_candidate_views", 50000)

    print(f"\n[Phase 2] Incremental scrape — {len(top_competitors)} top competitors")
    print(f"  Per channel: up to {max_videos} videos / {max_age_months} months")
    print(f"  Cached videos: stats refreshed only (1 unit each). New videos: full fetch.")
    print(f"  Note: {min_views:,}+ view filter applied at Phase 3; all videos stored for median calc.\n")

    total_videos = 0
    new_total = 0
    for i, tc in enumerate(top_competitors, 1):
        existing = load_video_cache(tc.id)
        prev_count = len(existing.get("videos", [])) if existing else 0

        print(f"  [{i}/{len(top_competitors)}] {tc.name} (cached: {prev_count})...", end=" ", flush=True)
        try:
            videos = _scrape_channel(yt, tc.id, max_videos, max_age_months, min_duration)
            write_video_cache(tc.id, {
                "channel_id": tc.id,
                "scraped_at": datetime.now().isoformat(),
                "scrape_depth": "primary",
                "videos": videos,
            })
            added = len(videos) - prev_count
            total_videos += len(videos)
            new_total += max(added, 0)
            print(f"{len(videos)} videos (+{max(added, 0)} new)")

            tc.last_scraped = today
            write_channels(channels_data)

        except QuotaExhaustedError as e:
            print(f"\n  QUOTA EXHAUSTED: {e}")
            raise
        except Exception as e:
            print(f"error: {e} (skipping)")
            continue

    mark_phase_complete(run_id, "phase2")
    print(f"\n  Done: {len(top_competitors)} channels, {total_videos} total videos ({new_total} newly fetched).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2: Incremental scrape of top competitors")
    parser.add_argument("--run-id", help="Run ID (default: auto-generated)")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg, run_id=args.run_id)
