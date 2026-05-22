"""
Phase 5 — SEO enrichment.

Enriches each cluster anchor with YouTube autocomplete suggestions
and Google Trends data (search volume proxy + trend direction).
Rate-limited: 1.5–2.5s between pytrends calls, 60s backoff on 429.
"""

from __future__ import annotations

import argparse

from utils.config import Config, load_config, get_setting
from utils.cache import (
    load_run_artifact, write_run_artifact,
    get_latest_run_artifact, generate_run_id,
)
from utils.seo import enrich_anchor


def run(
    cfg: Config,
    run_id: str | None = None,
    upstream: list[dict] | None = None,
) -> list[dict]:
    """
    Enrich anchors with SEO data. Returns enriched anchor list. Writes run artifact.
    """
    # Load from upstream or from disk artifact
    if upstream is not None:
        anchors = upstream
    else:
        if run_id:
            result = load_run_artifact(run_id, "scored_clusters")
        else:
            result = None
            found = get_latest_run_artifact("scored_clusters")
            if found:
                run_id, result = found

        if not result:
            print("[Phase 5] No scored_clusters artifact found. Run Phase 3+4 first.")
            return []
        anchors = result.get("anchors", [])

    run_id = run_id or generate_run_id()

    if not anchors:
        print("[Phase 5] No anchors to enrich.")
        return []

    seo_cfg = cfg.settings.get("seo", {})
    print(f"\n[Phase 5] SEO enrichment — {len(anchors)} topic candidates")
    print(f"  (Rate-limited: ~2s between pytrends calls)\n")

    enriched = []
    for i, anchor in enumerate(anchors, 1):
        title = anchor.get("topic", anchor.get("title", ""))
        print(f"  [{i}/{len(anchors)}] {title[:60]}...", end=" ", flush=True)

        seo_data = enrich_anchor(title, seo_cfg)
        enriched_anchor = {**anchor, **seo_data}
        enriched.append(enriched_anchor)

        vol = seo_data.get("search_volume_proxy", 0)
        trend = seo_data.get("trend_direction", "stable")
        richness = seo_data.get("keyword_richness", 0)
        print(f"vol={vol:.0f} trend={trend} suggestions={richness}")

    write_run_artifact(run_id, "seo_enriched", {"anchors": enriched, "run_id": run_id})
    print(f"\n  Written to output/runs/{run_id}_seo_enriched.json")
    return enriched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5: SEO enrichment")
    parser.add_argument("--run-id", help="Run ID to load scored_clusters artifact from")
    args = parser.parse_args()
    cfg = load_config()
    run(cfg, run_id=args.run_id)
