"""
Phase 1.5 — Competitor curation.

Scores discovered channels on 6 dimensions and picks the top 10
primary competitors. Shows ranked list, waits for user confirmation
on first curation, then writes top_competitors to channels.yaml.
"""

from __future__ import annotations

import argparse
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from utils.config import Config, ChannelsData, TopCompetitor, load_config, write_channels, get_setting
from utils.cache import load_video_cache, load_channel_meta

BASE_DIR = Path(__file__).parent.parent
NICHE_NOTES = BASE_DIR / "references" / "methodology" / "high-ticket-sales-niche-notes.md"


def _activity_score(uploads_last_90_days: int) -> float:
    if uploads_last_90_days == 0:
        return 0.0
    elif uploads_last_90_days <= 2:
        return 0.4
    elif uploads_last_90_days <= 6:
        return 0.7
    elif uploads_last_90_days <= 15:
        return 1.0
    else:
        return 0.85  # over-publishing penalty


def _trajectory_score(recent_median: float, overall_median: float) -> float:
    if overall_median <= 0:
        return 0.5
    ratio = recent_median / overall_median
    if ratio < 0.5:
        return 0.2
    elif ratio < 0.8:
        return 0.5
    elif ratio < 1.2:
        return 0.7
    elif ratio < 2.0:
        return 0.9
    else:
        return 1.0


def _tier_fit_score(tier: str) -> float:
    return {"peer-lower": 1.0, "peer-upper": 0.85, "emerging": 0.6, "aspirational": 0.4}.get(tier, 0.5)


def _engagement_score(median_engagement_rate: float, niche_baseline: float = 0.02) -> float:
    return min(median_engagement_rate / (niche_baseline * 2), 1.0)


def _niche_similarity_score(channel_id: str, niche_ref_texts: list[str], model_name: str) -> float:
    from utils.embeddings import mean_similarity_to_reference
    cache = load_video_cache(channel_id)
    if not cache or not cache.get("videos"):
        return 0.3  # default if no data
    titles = [v["title"] for v in cache["videos"][:30] if v.get("title")]
    if not titles:
        return 0.3
    sims = mean_similarity_to_reference(titles, niche_ref_texts, model_name)
    return min(float(statistics.mean(sims)), 1.0)


def _format_match_score(channel_id: str, min_duration: int = 600) -> float:
    cache = load_video_cache(channel_id)
    if not cache or not cache.get("videos"):
        return 0.5
    videos = cache["videos"][:30]
    if not videos:
        return 0.5
    long_form = sum(1 for v in videos if v.get("duration_seconds", 0) >= min_duration)
    return long_form / len(videos)


def _get_video_stats(channel_id: str) -> dict:
    """Compute stats from cached videos for a channel."""
    cache = load_video_cache(channel_id)
    if not cache or not cache.get("videos"):
        return {}

    videos = cache["videos"]
    now = datetime.now()
    cutoff_90 = now - timedelta(days=90)

    view_counts = [v.get("view_count", 0) for v in videos if v.get("view_count", 0) > 0]
    recent_videos = []
    uploads_last_90 = 0

    for v in videos:
        pub = v.get("published_at", "")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=None)
                if pub_dt >= cutoff_90:
                    uploads_last_90 += 1
                    recent_videos.append(v)
            except ValueError:
                pass

    overall_median = statistics.median(view_counts) if view_counts else 0
    recent_views = [v.get("view_count", 0) for v in videos[:10] if v.get("view_count", 0) > 0]
    recent_median = statistics.median(recent_views) if recent_views else 0

    engagement_rates = []
    for v in videos[:30]:
        views = v.get("view_count", 1)
        eng = (v.get("like_count", 0) + v.get("comment_count", 0)) / max(views, 1)
        engagement_rates.append(eng)
    median_engagement = statistics.median(engagement_rates) if engagement_rates else 0

    return {
        "uploads_last_90": uploads_last_90,
        "overall_median": overall_median,
        "recent_median": recent_median,
        "median_engagement": median_engagement,
    }


def run(cfg: Config, run_id: str | None = None, upstream=None, auto_confirm: bool = False) -> ChannelsData:
    """
    Score discovered channels and select top N primary competitors.
    Writes results to channels.yaml. Returns updated ChannelsData.
    """
    if not NICHE_NOTES.exists():
        raise FileNotFoundError(
            f"Niche notes file required for curation:\n  {NICHE_NOTES}\n"
            "Create it before running curation (see references/methodology/)."
        )

    model_name = get_setting(cfg, "clustering.embedding_model", "all-MiniLM-L6-v2")
    top_n = get_setting(cfg, "competitors.top_n", 10)
    weights = get_setting(cfg, "competitors.scoring_weights", {})

    w_niche = weights.get("niche_similarity", 0.25)
    w_format = weights.get("format_match", 0.20)
    w_activity = weights.get("activity", 0.15)
    w_trajectory = weights.get("performance_trajectory", 0.15)
    w_tier = weights.get("tier_fit", 0.15)
    w_engagement = weights.get("engagement_quality", 0.10)

    # Build niche reference texts
    niche_text = NICHE_NOTES.read_text(encoding="utf-8")
    seed_queries = cfg.settings.get("research", {}).get("seed_queries", [])
    niche_ref_texts = seed_queries + [niche_text[:2000]]

    channels = cfg.channels.channels
    if not channels:
        raise RuntimeError("No channels in channels.yaml. Run Phase 1 (discovery) first.")

    excluded_ids = {e["id"] for e in cfg.channels.excluded if isinstance(e, dict)}
    pinned_ids = {p["id"]: p for p in cfg.channels.pinned if isinstance(p, dict)}

    print(f"\n[Phase 1.5] Competitor curation — scoring {len(channels)} channels...")

    scored = []
    for i, ch in enumerate(channels, 1):
        if ch.id in excluded_ids:
            continue
        print(f"  [{i}/{len(channels)}] {ch.name} ({ch.subs:,} subs)...", end=" ", flush=True)

        stats = _get_video_stats(ch.id)

        niche_sim = _niche_similarity_score(ch.id, niche_ref_texts, model_name)
        format_match = _format_match_score(ch.id)
        activity = _activity_score(stats.get("uploads_last_90", 0))
        trajectory = _trajectory_score(
            stats.get("recent_median", 0),
            stats.get("overall_median", 0),
        )
        tier_fit = _tier_fit_score(ch.tier)
        engagement = _engagement_score(stats.get("median_engagement", 0))

        composite = (
            w_niche * niche_sim
            + w_format * format_match
            + w_activity * activity
            + w_trajectory * trajectory
            + w_tier * tier_fit
            + w_engagement * engagement
        )

        print(f"score {composite:.3f}")

        scored.append({
            "id": ch.id, "name": ch.name, "subs": ch.subs, "tier": ch.tier,
            "composite_score": composite,
            "sub_scores": {
                "niche_similarity": round(niche_sim, 3),
                "format_match": round(format_match, 3),
                "activity": round(activity, 3),
                "performance_trajectory": round(trajectory, 3),
                "tier_fit": round(tier_fit, 3),
                "engagement_quality": round(engagement, 3),
            },
        })

    # Sort by composite, but keep pinned channels at their existing ranks
    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    top = scored[:top_n]

    # Print table for user review
    print(f"\nTop {top_n} primary competitors:")
    print(f"  {'#':<3} {'Channel':<28} {'Subs':>8}  {'Tier':<12} {'Score'}")
    print(f"  {'-'*3} {'-'*28} {'-'*8}  {'-'*12} {'-'*5}")
    for i, c in enumerate(top, 1):
        subs_str = f"{c['subs']:,}"
        print(f"  {i:<3} {c['name']:<28} {subs_str:>8}  {c['tier']:<12} {c['composite_score']:.3f}")

    # First curation: wait for confirmation (skip if non-interactive)
    is_first_curation = not cfg.channels.top_competitors
    if is_first_curation and not auto_confirm:
        print("\nReply 'looks good' to proceed, or 'swap X for Y' to adjust (or just press Enter):")
        try:
            resp = input("> ").strip().lower()
        except EOFError:
            resp = ""
        if resp and resp not in ("looks good", "ok", "yes", "y", "proceed", ""):
            print("Curation paused. Edit config/channels.yaml manually if needed, then re-run.")
            return cfg.channels

    today = datetime.now().strftime("%Y-%m-%d")
    top_competitors = [
        TopCompetitor(
            rank=i + 1,
            id=c["id"],
            name=c["name"],
            subs=c["subs"],
            tier=c["tier"],
            composite_score=c["composite_score"],
            sub_scores=c["sub_scores"],
            curated_at=today,
            pinned=c["id"] in pinned_ids,
            notes="",
        )
        for i, c in enumerate(top)
    ]

    updated = ChannelsData(
        top_competitors=top_competitors,
        channels=cfg.channels.channels,
        pinned=cfg.channels.pinned,
        excluded=cfg.channels.excluded,
    )
    write_channels(updated)
    print(f"\n  Top {top_n} competitors written to config/channels.yaml")
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1.5: Curate top 10 competitors")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg, auto_confirm=args.yes)
