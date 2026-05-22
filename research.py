"""
Stage 1 orchestrator — runs the full research pipeline.

Usage:
  python research.py                        # full run, auto-resume from last checkpoint
  python research.py --from phase2          # skip discovery, start at scraping
  python research.py --from phase3          # re-score from existing cache
  python research.py --from phase5          # re-run SEO enrichment only
  python research.py --from phase6          # re-run ranking + sheet write only
  python research.py --phase1-only          # discover channels and stop
  python research.py --rediscover           # force re-run phase 1
  python research.py --recurate             # force re-run phase 1.5
  python research.py --run-id 2026-05-20-1423  # resume a specific run
"""

from __future__ import annotations

import argparse
import sys

from utils.config import load_config, needs_discovery, needs_curation
from utils.cache import generate_run_id

PHASE_ORDER = ["phase1", "phase1_5", "phase2", "phase3", "phase5", "phase6"]


def parse_args():
    p = argparse.ArgumentParser(description="YouTube research pipeline — Stage 1")
    p.add_argument(
        "--from",
        dest="from_phase",
        choices=PHASE_ORDER,
        default=None,
        help="Skip all phases before this one",
    )
    p.add_argument("--phase1-only", action="store_true", help="Run Phase 1 and stop")
    p.add_argument("--rediscover", action="store_true", help="Force re-run Phase 1 even if recent")
    p.add_argument("--recurate", action="store_true", help="Force re-run Phase 1.5 even if recent")
    p.add_argument("--run-id", default=None, help="Resume or target a specific run ID")
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  Sales YT Research Pipeline")
    print("=" * 60)

    try:
        cfg = load_config()
    except Exception as e:
        print(f"\nConfig error: {e}")
        sys.exit(1)

    run_id = args.run_id or generate_run_id()
    from_phase = args.from_phase

    # Determine starting phase index
    start_idx = 0
    if from_phase:
        start_idx = PHASE_ORDER.index(from_phase)

    channels_data = cfg.channels
    anchors = None
    enriched = None

    # ── Phase 1: Channel discovery ─────────────────────────────────────────────
    if start_idx <= 0:
        should_run = args.rediscover or needs_discovery(cfg)
        if should_run:
            from scripts.phase1_discover import run as phase1_run
            channels_data = phase1_run(cfg, run_id=run_id)
            # Reload config so subsequent phases see the updated channels
            cfg = load_config()
        else:
            print("\n[Phase 1] Skipped — channels.yaml is fresh (< 30 days old)")
            print("  Use --rediscover to force re-run")
    else:
        print("\n[Phase 1] Skipped (--from specified)")

    if args.phase1_only:
        print("\nStopped after Phase 1 (--phase1-only flag).")
        return

    # ── Phase 1.5: Competitor curation ────────────────────────────────────────
    if start_idx <= 1:
        should_run = args.recurate or needs_curation(cfg)
        if should_run:
            from scripts.phase1_5_curate import run as phase1_5_run
            channels_data = phase1_5_run(cfg, run_id=run_id)
            cfg = load_config()
        else:
            print("\n[Phase 1.5] Skipped — top competitors curated recently")
            print("  Use --recurate to force re-curation")
    else:
        print("\n[Phase 1.5] Skipped (--from specified)")

    # ── Phase 2: Video scraping ────────────────────────────────────────────────
    if start_idx <= 2:
        from scripts.phase2_scrape import run as phase2_run
        phase2_run(cfg, run_id=run_id)
    else:
        print("\n[Phase 2] Skipped (--from specified)")

    # ── Phase 3+4: Scoring and clustering ─────────────────────────────────────
    if start_idx <= 3:
        from scripts.phase3_4_score_cluster import run as phase34_run
        anchors = phase34_run(cfg, run_id=run_id)
    else:
        print("\n[Phase 3+4] Skipped (--from specified)")

    # ── Phase 5: SEO enrichment ────────────────────────────────────────────────
    if start_idx <= 4:
        from scripts.phase5_seo import run as phase5_run
        enriched = phase5_seo_run = phase5_run(cfg, run_id=run_id, upstream=anchors)
    else:
        print("\n[Phase 5] Skipped (--from specified)")

    # ── Phase 6+7: Ranking + Sheet ─────────────────────────────────────────────
    if start_idx <= 5:
        from scripts.phase6_7_rank_sheet import run as phase67_run
        sheet_url = phase67_run(cfg, run_id=run_id, upstream=enriched)
    else:
        print("\n[Phase 6+7] Skipped (--from specified)")
        sheet_url = ""

    print("\n" + "=" * 60)
    if sheet_url:
        print(f"  Top 10 topic candidates are in the sheet:")
        print(f"  {sheet_url}")
        print(f"\n  Top 10 competitors are in the second tab.")
        print(f"\n  Reply with the row number to generate a script:")
        print(f"    python script_writer.py --row <number>")
    else:
        print("  Pipeline completed (sheet URL unavailable — check above for errors)")
    print("=" * 60)


if __name__ == "__main__":
    main()
