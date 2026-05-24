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
