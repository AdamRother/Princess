"""
Phase 2 — Video scraping.

Scrapes ONLY the top competitors from channels.yaml.
Every run is a FULL fresh scrape — old cache is deleted before fetching.
View count filter (50k+) is applied in Phase 3 when selecting breakout
candidates; all videos are stored here so median calculation stays accurate.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from utils.config import Config, load_config, load_channels, write_channels
from utils.youtube_api import (
    build_client, get_channel_metadata, list_playlist_items,
    get_video_details, QuotaExhaustedError,
)
from utils.cache import (
    write_video_cache, load_channel_meta, write_channel_meta,
    mark_phase_complete, generate_run_id,
)

_RAW_VIDEOS_DIR = Path(__file__).parent.parent / "output" / "raw" / "videos"


def _clear_video_cache() -> None:
    """Delete all cached video data so this run starts completely fresh."""
    if _RAW_VIDEOS_DIR.exists():
        shutil.rmtree(_RAW_VIDEOS_DIR)
    _RAW_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    print("  [Phase 2] Old video cache cleared — fresh scrape starting.")


def _scrape_channel(
    yt,
    channel_id: str,
    max_videos: int,
    max_age_months: int,
    min_duration: int,
) -> list[dict]:
    """
    Full scrape of one channel — no incremental caching.
    Returns all videos that pass duration + age filters.
    """
    cutoff = datetime.now() - timedelta(days=max_age_months * 30)

    # Ensure uploads playlist ID is available
    meta = load_channel_meta(channel_id) or {}
    if not meta.get("uploads_playlist_id"):
        channel_metas = get_channel_metadata(yt, [channel_id])
        if not channel_metas:
            return []
        m = channel_metas[0]
        meta = {
            "id": m.id, "title": m.title,
            "subs": m.subscriber_count, "views": m.view_count,
            "uploads_playlist_id": m.uploads_playlist_id,
        }
        write_channel_meta(channel_id, meta)

    playlist_id = meta.get("uploads_playlist_id", "")
    if not playlist_id:
        return []

    # Fresh fetch — no stop_at_ids
    video_ids = list_playlist_items(yt, playlist_id, stop_at_ids=set(), max_items=max_videos)
    if not video_ids:
        return []

    all_details = get_video_details(yt, video_ids)

    videos = []
    for d in all_details:
        if d.duration_seconds < min_duration:
            continue
        try:
            pub = datetime.fromisoformat(d.published_at.replace("Z", "+00:00")).replace(tzinfo=None)
            if pub < cutoff:
                continue
        except (ValueError, AttributeError):
            pass
        videos.append({
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

    return videos


def run(cfg: Config, run_id: str | None = None, upstream=None) -> None:
    """
    Full fresh scrape of all top competitors.
    Always clears old cache first and re-fetches everything from scratch.
    Only top competitors are scraped — no secondary channels.
    """
    run_id = run_id or generate_run_id()
    channels_data = load_channels()

    top_competitors = channels_data.top_competitors or []
    if not top_competitors:
        print("[Phase 2] No top competitors found. Run Phase 1.5 first.")
        return

    _clear_video_cache()

    yt = build_client(cfg.youtube_api_key)
    today = datetime.now().strftime("%Y-%m-%d")

    depth = cfg.settings.get("scrape_depth", {}).get("primary", {})
    max_videos = depth.get("max_videos", 100)
    max_age_months = depth.get("max_age_months", 24)
    min_duration = cfg.settings.get("video_filters", {}).get("min_duration_seconds", 60)
    min_views = cfg.settings.get("video_filters", {}).get("min_candidate_views", 50000)

    print(f"\n[Phase 2] Full fresh scrape — {len(top_competitors)} top competitors")
    print(f"  Per channel: up to {max_videos} videos / {max_age_months} months")
    print(f"  Note: all view counts stored; {min_views:,}+ view filter applied at Phase 3\n")

    total_videos = 0
    for i, tc in enumerate(top_competitors, 1):
        print(f"  [{i}/{len(top_competitors)}] {tc.name}...", end=" ", flush=True)
        try:
            videos = _scrape_channel(yt, tc.id, max_videos, max_age_months, min_duration)
            write_video_cache(tc.id, {
                "channel_id": tc.id,
                "scraped_at": datetime.now().isoformat(),
                "scrape_depth": "primary",
                "videos": videos,
            })
            total_videos += len(videos)
            print(f"{len(videos)} videos")

            tc.last_scraped = today
            write_channels(channels_data)

        except QuotaExhaustedError as e:
            print(f"\n  QUOTA EXHAUSTED: {e}")
            raise
        except Exception as e:
            print(f"error: {e} (skipping)")
            continue

    mark_phase_complete(run_id, "phase2")
    print(f"\n  Done: {len(top_competitors)} channels, {total_videos} total videos cached.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2: Full fresh scrape of top competitors")
    parser.add_argument("--run-id", help="Run ID (default: auto-generated)")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg, run_id=args.run_id)
