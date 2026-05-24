"""Atomic read/write for output/raw/ video caches and output/runs/ run artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent.parent
VIDEOS_DIR = BASE_DIR / "output" / "raw" / "videos"
CHANNELS_DIR = BASE_DIR / "output" / "raw" / "channels"
TRANSCRIPTS_DIR = BASE_DIR / "output" / "raw" / "transcripts"
RUNS_DIR = BASE_DIR / "output" / "runs"


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Video cache ──────────────────────────────────────────────────────────────

def load_video_cache(channel_id: str) -> dict | None:
    """Returns the full cache dict for a channel, or None if not cached yet."""
    return _read_json(VIDEOS_DIR / f"{channel_id}.json")


def write_video_cache(channel_id: str, data: dict) -> None:
    _write_json_atomic(VIDEOS_DIR / f"{channel_id}.json", data)


def load_channel_meta(channel_id: str) -> dict | None:
    return _read_json(CHANNELS_DIR / f"{channel_id}.json")


def write_channel_meta(channel_id: str, data: dict) -> None:
    _write_json_atomic(CHANNELS_DIR / f"{channel_id}.json", data)


def list_cached_channel_ids() -> list[str]:
    if not VIDEOS_DIR.exists():
        return []
    return [p.stem for p in VIDEOS_DIR.glob("*.json")]


# ── Run artifacts ─────────────────────────────────────────────────────────────

def load_run_artifact(run_id: str, phase: str) -> dict | None:
    """Load output/runs/{run_id}_{phase}.json. Returns None if missing."""
    return _read_json(RUNS_DIR / f"{run_id}_{phase}.json")


def write_run_artifact(run_id: str, phase: str, data: dict) -> None:
    _write_json_atomic(RUNS_DIR / f"{run_id}_{phase}.json", data)


def mark_phase_complete(run_id: str, phase: str) -> None:
    """Write a zero-byte flag file signalling a phase completed cleanly."""
    flag = RUNS_DIR / f"{run_id}_{phase}_complete.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()


def is_phase_complete(run_id: str, phase: str) -> bool:
    return (RUNS_DIR / f"{run_id}_{phase}_complete.flag").exists()


def get_latest_run_artifact(phase: str) -> tuple[str, dict] | None:
    """
    Find the most recent run that has an artifact for the given phase.
    Returns (run_id, data) or None.
    """
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(RUNS_DIR.glob(f"*_{phase}.json"), reverse=True)
    for path in candidates:
        run_id = path.name.replace(f"_{phase}.json", "")
        data = _read_json(path)
        if data is not None:
            return run_id, data
    return None


def list_run_ids() -> list[str]:
    """List all run IDs that have at least one artifact, sorted newest first."""
    if not RUNS_DIR.exists():
        return []
    ids = set()
    for p in RUNS_DIR.iterdir():
        if p.suffix in (".json", ".flag"):
            # run_id is everything before the first underscore-delimited phase name
            parts = p.stem.split("_")
            # run_id format is YYYY-MM-DD-HHMM, so first 4 parts
            run_id = "_".join(parts[:4]) if len(parts) >= 4 else parts[0]
            ids.add(run_id)
    return sorted(ids, reverse=True)


def generate_run_id() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M")


# ── Video field updates + status tracking ────────────────────────────────────

def update_video_fields(channel_id: str, video_id: str, updates: dict) -> bool:
    """Update specific fields on one video in its channel cache. Returns True if found."""
    cache = load_video_cache(channel_id)
    if not cache:
        return False
    changed = False
    for v in cache.get("videos", []):
        if v.get("id") == video_id:
            v.update(updates)
            changed = True
            break
    if changed:
        write_video_cache(channel_id, cache)
    return changed


def mark_video_scripted(video_id: str) -> bool:
    """
    Search all channel caches for video_id and set status='scripted'.
    The next research run will drop it from the candidate pool.
    Returns True if found and marked.
    """
    for channel_id in list_cached_channel_ids():
        if update_video_fields(channel_id, video_id, {"status": "scripted"}):
            return True
    return False


def update_channel_performance(channel_id: str, scored_videos: list[dict]) -> None:
    """
    Write computed performance fields back to each video in the channel cache.
    scored_videos is the output of _score_video() — same list loaded from cache
    but with performance metrics added.
    """
    cache = load_video_cache(channel_id)
    if not cache:
        return

    scored_by_id = {v["id"]: v for v in scored_videos if "id" in v}
    updated = False
    for v in cache.get("videos", []):
        scored = scored_by_id.get(v.get("id", ""))
        if not scored:
            continue
        new_perf = {
            "views_per_day": round(scored.get("views_per_day", 0), 2),
            "outlier_score": round(scored.get("outlier_score", 0), 3),
            "engagement_rate": round(scored.get("engagement_rate", 0), 4),
            "age_weighted_score": round(scored.get("age_weighted_score", 0), 2),
            "is_breakout": scored.get("is_breakout", False),
            "days_since_publish": scored.get("days_since_publish", 0),
            "channel_median_views": round(scored.get("channel_median_views", 0), 1),
            "summary": (
                f"{scored.get('outlier_score', 0):.1f}x median · "
                f"{scored.get('view_count', 0):,} views · "
                f"{scored.get('days_since_publish', 0)}d old"
            ),
        }
        if v.get("performance") != new_perf:
            v["performance"] = new_perf
            updated = True

    if updated:
        write_video_cache(channel_id, cache)


# ── Transcript cache ──────────────────────────────────────────────────────────

def load_transcript(video_id: str) -> str | None:
    path = TRANSCRIPTS_DIR / f"{video_id}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_transcript(video_id: str, text: str) -> None:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPTS_DIR / f"{video_id}.txt"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
