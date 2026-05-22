"""
Phase 1 — Channel discovery.

Searches YouTube for competitor channels using seed queries,
fetches their metadata, filters for active channels, assigns tiers,
and writes to config/channels.yaml.
"""

from __future__ import annotations

import argparse
import statistics
from datetime import datetime

from utils.config import Config, ChannelEntry, ChannelsData, load_config, write_channels
from utils.youtube_api import (
    build_client, search_channels, get_channel_metadata,
    list_playlist_items, get_video_details, assign_tier, QuotaExhaustedError,
)
from utils.cache import write_channel_meta


def run(cfg: Config, run_id: str | None = None, upstream=None) -> ChannelsData:
    """
    Discover channels from seed queries and write to channels.yaml.
    Returns updated ChannelsData.
    """
    yt = build_client(cfg.youtube_api_key)
    seed_queries = cfg.settings.get("research", {}).get("seed_queries", [])
    max_channels = cfg.settings.get("research", {}).get("channels_to_track_max", 25)
    excluded_ids = {e["id"] for e in cfg.channels.excluded if isinstance(e, dict)}

    print(f"\n[Phase 1] Channel discovery")
    print(f"  Searching {len(seed_queries)} seed queries...")

    # Collect unique channel IDs from all seed queries
    all_channel_ids: set[str] = set()
    for i, query in enumerate(seed_queries, 1):
        print(f"  [{i}/{len(seed_queries)}] '{query}'", end=" ", flush=True)
        try:
            ids = search_channels(yt, query, max_results=25)
            new = set(ids) - all_channel_ids
            all_channel_ids.update(ids)
            print(f"→ {len(ids)} results, {len(new)} new")
        except QuotaExhaustedError as e:
            print(f"\n  {e}")
            raise
        except Exception as e:
            print(f"→ error: {e}")

    print(f"\n  Found {len(all_channel_ids)} unique channels. Fetching metadata...")

    # Remove excluded channels
    all_channel_ids -= excluded_ids

    # Fetch metadata in batches
    channel_ids_list = list(all_channel_ids)
    all_meta = get_channel_metadata(yt, channel_ids_list)

    # Filter and qualify channels
    kept: list[ChannelEntry] = []
    today = datetime.now().strftime("%Y-%m-%d")

    for meta in all_meta:
        # Cache the metadata
        write_channel_meta(meta.id, {
            "id": meta.id, "title": meta.title, "subs": meta.subscriber_count,
            "views": meta.view_count, "uploads_playlist_id": meta.uploads_playlist_id,
        })

        # Quick activity check: get last 30 video IDs
        recent_ids = []
        if meta.uploads_playlist_id:
            try:
                recent_ids = list_playlist_items(yt, meta.uploads_playlist_id, max_items=30)
            except Exception:
                pass

        # Filter: must have >= 5 recent videos OR >= 10k subs OR >= 100k total views
        if len(recent_ids) < 5 and meta.subscriber_count < 10000 and meta.view_count < 100000:
            continue

        tier = assign_tier(meta.subscriber_count, cfg.settings)
        kept.append(ChannelEntry(
            id=meta.id,
            name=meta.title,
            subs=meta.subscriber_count,
            tier=tier,
            added=today,
            last_scraped="",
        ))

    # Limit to max
    kept = kept[:max_channels]
    kept.sort(key=lambda c: c.subs, reverse=True)

    # Merge with any existing pinned channels
    pinned = cfg.channels.pinned or []
    pinned_ids = {p["id"] for p in pinned if isinstance(p, dict)}
    for p in pinned:
        if isinstance(p, dict) and p["id"] not in {c.id for c in kept}:
            kept.append(ChannelEntry(
                id=p["id"], name=p.get("name", ""), subs=0,
                tier="emerging", added=today, last_scraped="",
            ))

    updated = ChannelsData(
        top_competitors=cfg.channels.top_competitors,
        channels=kept,
        pinned=cfg.channels.pinned,
        excluded=cfg.channels.excluded,
    )
    write_channels(updated)

    tier_counts = {}
    for c in kept:
        tier_counts[c.tier] = tier_counts.get(c.tier, 0) + 1
    tier_str = ", ".join(f"{v} {k}" for k, v in sorted(tier_counts.items()))

    print(f"\n  Discovered {len(kept)} channels ({tier_str})")
    print(f"  Written to config/channels.yaml")
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1: Discover competitor channels")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg)
