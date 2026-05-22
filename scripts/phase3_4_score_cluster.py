"""
Phase 3+4 — Performance scoring and topic clustering.

Loads all cached video data, computes performance metrics,
identifies breakout videos, embeds titles, clusters with DBSCAN,
and picks cluster anchors as topic candidates.
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
from datetime import datetime

from utils.config import Config, load_config, get_setting
from utils.cache import (
    list_cached_channel_ids, load_video_cache, load_channel_meta,
    write_run_artifact, get_latest_run_artifact, generate_run_id,
)

# Keyword set for niche relevance filtering — video titles must contain at least one.
# Covers the full sales coaching spectrum: closing, calls, prospecting, mindset, training.
NICHE_KEYWORDS = {
    # Core sales verbs / nouns
    "sales", "selling", "sell", "sold",
    # Closing
    "close", "closing", "closer",
    # Call types
    "sales call", "discovery call", "cold call", "cold dm", "cold email",
    "phone sales", "sales conversation",
    # Prospecting & outreach
    "prospect", "prospecting", "outreach", "lead generation", "lead gen",
    # Appointment / setter track
    "appointment set", "appointment setting", "setter",
    # Objections & follow-up
    "objection", "objection handling", "follow up", "follow-up", "followup", "rejection",
    # High-ticket / remote
    "high ticket", "high-ticket", "remote clos", "remote sales",
    # Business outcomes
    "commission", "quota", "revenue", "conversion", "close rate", "close deals",
    "income", "earn", "make money",
    # Coaching / training
    "sales coach", "sales coaching", "sales training", "sales tips", "sales technique",
    "sales strategy", "sales script", "sales course",
    # Skills / mindset
    "pitch", "mindset", "tonality", "rapport",
    "negotiate", "negotiation", "script", "framework",
    # Broader sales education
    "b2b sales", "b2c sales", "consultative", "persuasion", "influence",
    "buyer", "client acquisition", "customer acquisition",
}


# Topics that match NICHE_KEYWORDS but are off-niche (car, real estate, pharma, etc.)
NICHE_EXCLUSIONS = {
    "car sales", "car salesm", "car dealer", "car lot", "auto sales", "dealership",
    "real estate", "mortgage", "insurance sales", "pharma sales", "pharmaceutical",
    "timeshare", "door to door", "door-to-door", "retail sales", "mlm", "network marketing",
}

# Interview / podcast / reaction format signals — we only want solo talking-head videos.
# Titles containing these are skipped regardless of niche relevance.
FORMAT_EXCLUSIONS = {
    "interview", "podcast", " ep ", " ep.", "episode", "feat.", "ft.",
    "| with ", " with ", "asks me", "reacts to", "reacting to",
    "day in my life", "vlog", "my story", "qa ", "q&a", "q & a",
    "ama ", "ask me", "story time",
}


def _is_niche_relevant(title: str) -> bool:
    """Return True if the video title is in-niche, not excluded, and not interview/podcast format."""
    t = title.lower()
    if any(excl in t for excl in NICHE_EXCLUSIONS):
        return False
    if any(fmt in t for fmt in FORMAT_EXCLUSIONS):
        return False
    return any(kw in t for kw in NICHE_KEYWORDS)


def _is_english(title: str) -> bool:
    """Return True if the title appears to be primarily English (>75% ASCII printable)."""
    if not title:
        return False
    ascii_chars = sum(1 for c in title if ord(c) < 128 and c.isprintable())
    return ascii_chars / len(title) >= 0.75


def _clean_topic_name(raw_title: str) -> str:
    """Strip emojis, hashtags, ellipsis, and noise from a video title."""
    clean = re.sub(r'#\S+', '', raw_title)
    clean = re.sub(r'[^\x00-\x7F]+', '', clean)   # strip non-ASCII (emojis)
    clean = re.sub(r'\.\.\.+', '', clean)           # remove trailing ellipsis
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = clean.strip('!?.,;: ')
    if len(clean) > 72:
        trunc = clean[:69]
        last_space = trunc.rfind(' ')
        clean = (trunc[:last_space] if last_space > 45 else trunc) + '...'
    return clean


def _score_video(
    video: dict,
    channel_median_views: float,
    channel_median_vpd: float,
    outlier_threshold: float = 2.0,
    min_absolute_views: int = 3000,
) -> dict:
    """Add performance metrics to a video dict."""
    pub_raw = video.get("published_at", "")
    try:
        pub = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        days_since = max((datetime.now() - pub).days, 1)
    except (ValueError, TypeError):
        days_since = 365

    views = video.get("view_count", 0)
    likes = video.get("like_count", 0)
    comments = video.get("comment_count", 0)

    views_per_day = views / days_since
    outlier_score = views / max(channel_median_views, 1)
    engagement_rate = (likes + comments) / max(views, 1)
    age_weighted_score = views_per_day * math.log(days_since + 7)

    # Primary condition: outlier relative to its channel + consistently above median vpd
    # Secondary condition: high absolute views (catches top performers from high-median channels)
    is_breakout = (
        (outlier_score >= outlier_threshold and views_per_day >= channel_median_vpd * 1.5)
        or (views >= min_absolute_views and outlier_score >= 1.5)
    )

    return {
        **video,
        "days_since_publish": days_since,
        "views_per_day": views_per_day,
        "channel_median_views": channel_median_views,
        "outlier_score": outlier_score,
        "engagement_rate": engagement_rate,
        "age_weighted_score": age_weighted_score,
        "is_breakout": is_breakout,
    }


def _get_channel_medians(videos: list[dict]) -> tuple[float, float]:
    """Returns (median_views, median_views_per_day) for a channel's video list."""
    view_counts = [v.get("view_count", 0) for v in videos if v.get("view_count", 0) > 0]
    if not view_counts:
        return 1.0, 0.1

    median_views = statistics.median(view_counts)

    vpds = []
    for v in videos:
        pub_raw = v.get("published_at", "")
        views = v.get("view_count", 0)
        try:
            pub = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            days = max((datetime.now() - pub).days, 1)
            vpds.append(views / days)
        except (ValueError, TypeError):
            pass
    median_vpd = statistics.median(vpds) if vpds else 0.1

    return median_views, median_vpd


def run(cfg: Config, run_id: str | None = None, upstream=None) -> list[dict]:
    """
    Score all cached videos, find breakouts, cluster by topic.
    Returns list of cluster anchor dicts. Writes run artifact.
    """
    run_id = run_id or generate_run_id()
    model_name = get_setting(cfg, "clustering.embedding_model", "all-MiniLM-L6-v2")
    dbscan_eps = get_setting(cfg, "clustering.dbscan_eps", 0.4)
    dbscan_min_samples = get_setting(cfg, "clustering.dbscan_min_samples", 2)
    outlier_threshold = get_setting(cfg, "scoring.outlier_threshold", 2.0)
    min_absolute_views = get_setting(cfg, "scoring.min_absolute_views", 3000)
    min_candidate_views = get_setting(cfg, "video_filters.min_candidate_views", 3000)
    max_age_months = get_setting(cfg, "video_filters.max_age_months", 24)
    max_age_days = max_age_months * 30
    trending_max_days = get_setting(cfg, "video_filters.trending_max_days", 90)
    evergreen_min_days = get_setting(cfg, "video_filters.evergreen_min_days", 90)
    evergreen_min_views = get_setting(cfg, "video_filters.evergreen_min_views", 8000)

    top_ids = {tc.id for tc in (cfg.channels.top_competitors or [])}

    # Build excluded set — cfg.channels.excluded can be list[str] or list[dict]
    excluded_ids: set[str] = set()
    for item in (cfg.channels.excluded or []):
        if isinstance(item, str):
            excluded_ids.add(item)
        elif isinstance(item, dict):
            if item.get("id"):
                excluded_ids.add(item["id"])

    channel_ids = list_cached_channel_ids()

    if not channel_ids:
        print("[Phase 3+4] No cached video data. Run Phase 2 first.")
        return []

    usable = [cid for cid in channel_ids if cid not in excluded_ids]
    skipped = len(channel_ids) - len(usable)
    print(f"\n[Phase 3+4] Scoring and clustering — {len(usable)} channels ({skipped} excluded)")

    all_candidates = []

    for channel_id in usable:
        cache = load_video_cache(channel_id)
        if not cache or not cache.get("videos"):
            continue

        videos = cache["videos"]
        median_views, median_vpd = _get_channel_medians(videos)

        # Get channel name once per channel
        meta = load_channel_meta(channel_id)
        channel_name = meta.get("title", channel_id) if meta else channel_id

        for v in videos:
            scored = _score_video(v, median_views, median_vpd, outlier_threshold, min_absolute_views)
            scored["channel_id"] = channel_id
            scored["channel_name"] = channel_name
            scored["primary_competitor"] = channel_id in top_ids

            title = scored.get("title", "")
            days = scored.get("days_since_publish", 999)
            views = scored.get("view_count", 0)

            # Trending bucket: recent + enough views to be meaningful
            is_trending = days <= trending_max_days and views >= min_candidate_views
            # Evergreen bucket: older + higher view bar (needs proven staying power)
            is_evergreen = days > evergreen_min_days and days <= max_age_days and views >= evergreen_min_views

            if ((is_trending or is_evergreen)
                    and scored.get("duration_seconds", 0) >= 600
                    and _is_english(title)
                    and _is_niche_relevant(title)):
                scored["recency_bucket"] = "trending" if is_trending else "evergreen"
                all_candidates.append(scored)

    if not all_candidates:
        print("  No candidates found. Check channels.yaml has scraped data, or lower min_candidate_views.")
        return []

    print(f"  Found {len(all_candidates)} candidate videos across {len(channel_ids)} channels")

    # Deduplicate by video ID only — keep every unique video as its own topic.
    # Each video has a distinct angle, hook, or problem framing worth modeling separately.
    # We do NOT cluster: grouping "cold call" videos together and picking one would throw
    # away the other angles, which is exactly the signal we want to keep.
    seen_ids: set[str] = set()
    anchors = []
    for v in all_candidates:
        vid_id = v.get("id", v.get("video_id", ""))
        if vid_id in seen_ids:
            continue
        seen_ids.add(vid_id)

        anchor = dict(v)
        anchor["cluster_id"] = 0
        anchor["cluster_size"] = 1
        anchor["cluster_title_variants"] = []
        anchor["topic"] = _clean_topic_name(anchor["title"])
        anchor["source_channel"] = anchor["channel_name"]
        anchor["source_title"] = anchor["title"]
        anchor["source_url"] = f"https://www.youtube.com/watch?v={vid_id}"
        anchor["source_views"] = anchor.get("view_count", 0)
        anchor["source_tier"] = _get_channel_tier(anchor["channel_id"], cfg)
        anchors.append(anchor)

    print(f"  {len(anchors)} unique topic candidates (no clustering — every video kept as its own angle)")

    write_run_artifact(run_id, "scored_clusters", {"anchors": anchors, "run_id": run_id})
    print(f"  Written to output/runs/{run_id}_scored_clusters.json")
    return anchors


def _get_channel_tier(channel_id: str, cfg: Config) -> str:
    for ch in cfg.channels.channels:
        if ch.id == channel_id:
            return ch.tier
    for tc in cfg.channels.top_competitors:
        if tc.id == channel_id:
            return tc.tier
    return "unknown"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3+4: Score videos and cluster topics")
    parser.add_argument("--run-id", help="Run ID (default: auto-generated)")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg, run_id=args.run_id)
