"""Load and validate all config: .env (secrets), settings.yaml, channels.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv, set_key, dotenv_values

BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
CHANNELS_PATH = CONFIG_DIR / "channels.yaml"

# Load .env into os.environ on import
load_dotenv(ENV_PATH, override=True)


class ConfigError(Exception):
    pass


@dataclass
class ChannelEntry:
    id: str
    name: str
    subs: int = 0
    tier: str = "emerging"
    added: str = ""
    last_scraped: str = ""


@dataclass
class TopCompetitor:
    rank: int
    id: str
    name: str
    subs: int = 0
    tier: str = "peer-lower"
    composite_score: float = 0.0
    sub_scores: dict = field(default_factory=dict)
    curated_at: str = ""
    pinned: bool = False
    notes: str = ""


@dataclass
class ChannelsData:
    top_competitors: list[TopCompetitor] = field(default_factory=list)
    channels: list[ChannelEntry] = field(default_factory=list)
    pinned: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)


@dataclass
class Config:
    youtube_api_key: str
    target_sheet_id: str
    target_docs_folder_id: str
    client_secrets_path: str
    settings: dict
    channels: ChannelsData
    client_channel_url: str = ""
    client_niche_description: str = ""


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _env(key: str, default: str = "") -> str:
    """Read a value from .env / environment. Key is case-insensitive."""
    return os.environ.get(key.upper(), os.environ.get(key.lower(), default))


def get_secret(key: str) -> str:
    val = _env(key)
    if not val:
        raise ConfigError(
            f"Missing required secret: '{key.upper()}'\n"
            f"Open .env and fill in this value.\n"
            f"See .env.example for the full list of required keys."
        )
    return val


def load_channels() -> ChannelsData:
    data = _load_yaml(CHANNELS_PATH)

    top_competitors = []
    for item in (data.get("top_competitors") or []):
        if isinstance(item, dict):
            top_competitors.append(TopCompetitor(
                rank=item.get("rank", 0),
                id=item.get("id", ""),
                name=item.get("name", ""),
                subs=item.get("subs", 0),
                tier=item.get("tier", "emerging"),
                composite_score=item.get("composite_score", 0.0),
                sub_scores=item.get("sub_scores", {}),
                curated_at=str(item.get("curated_at", "")),
                pinned=item.get("pinned", False),
                notes=item.get("notes", ""),
            ))

    channels = []
    for item in (data.get("channels") or []):
        if isinstance(item, dict):
            channels.append(ChannelEntry(
                id=item.get("id", ""),
                name=item.get("name", ""),
                subs=item.get("subs", 0),
                tier=item.get("tier", "emerging"),
                added=str(item.get("added", "")),
                last_scraped=str(item.get("last_scraped", "")),
            ))

    return ChannelsData(
        top_competitors=top_competitors,
        channels=channels,
        pinned=data.get("pinned") or [],
        excluded=data.get("excluded") or [],
    )


def write_channels(data: ChannelsData) -> None:
    """Write updated channels.yaml atomically."""
    out: dict[str, Any] = {}

    if data.top_competitors:
        out["top_competitors"] = [
            {
                "rank": c.rank, "id": c.id, "name": c.name, "subs": c.subs,
                "tier": c.tier, "composite_score": round(c.composite_score, 4),
                "sub_scores": c.sub_scores, "curated_at": c.curated_at,
                "pinned": c.pinned, "notes": c.notes,
            }
            for c in data.top_competitors
        ]
    else:
        out["top_competitors"] = []

    if data.channels:
        out["channels"] = [
            {
                "id": c.id, "name": c.name, "subs": c.subs, "tier": c.tier,
                "added": c.added, "last_scraped": c.last_scraped,
            }
            for c in data.channels
        ]
    else:
        out["channels"] = []

    out["pinned"] = data.pinned or []
    out["excluded"] = data.excluded or []

    tmp = CHANNELS_PATH.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(out, f, default_flow_style=False, allow_unicode=True)
    os.replace(tmp, CHANNELS_PATH)


def load_config() -> Config:
    settings = _load_yaml(SETTINGS_PATH)
    channels = load_channels()

    def _req(key: str) -> str:
        val = _env(key)
        if not val:
            raise ConfigError(
                f"Missing required secret: '{key.upper()}'\n"
                f"Open .env and fill in this value.\n"
                f"See .env.example for the full list of required keys."
            )
        return val

    return Config(
        youtube_api_key=_req("YOUTUBE_API_KEY"),
        target_sheet_id=_env("TARGET_SHEET_ID", "auto"),
        target_docs_folder_id=_env("TARGET_DOCS_FOLDER_ID", "auto"),
        client_secrets_path=_env("CLIENT_SECRETS_PATH", "config/client_secrets.json"),
        settings=settings,
        channels=channels,
        client_channel_url=_env("CLIENT_CHANNEL_URL", ""),
        client_niche_description=_env(
            "CLIENT_NICHE_DESCRIPTION",
            "Female sales coach teaching closers, setters, and founders how to sell on calls",
        ),
    )


def needs_discovery(cfg: Config) -> bool:
    """True if channels list is empty or all entries are stale (>30 days)."""
    if not cfg.channels.channels:
        return True
    cutoff = datetime.now() - timedelta(days=30)
    for ch in cfg.channels.channels:
        if ch.last_scraped:
            try:
                scraped = datetime.fromisoformat(ch.last_scraped[:10])
                if scraped >= cutoff:
                    return False
            except ValueError:
                pass
    return True


def needs_curation(cfg: Config) -> bool:
    """True if top_competitors is empty or curated_at is older than recuration_days."""
    if not cfg.channels.top_competitors:
        return True
    recuration_days = cfg.settings.get("competitors", {}).get("recuration_days", 60)
    cutoff = datetime.now() - timedelta(days=recuration_days)
    for tc in cfg.channels.top_competitors:
        if tc.curated_at:
            try:
                curated = datetime.fromisoformat(tc.curated_at[:10])
                if curated >= cutoff:
                    return False
            except ValueError:
                pass
    return True


def get_setting(cfg: Config, path: str, default: Any = None) -> Any:
    """Dot-path accessor: get_setting(cfg, 'clustering.dbscan_eps') -> 0.4"""
    parts = path.split(".")
    node = cfg.settings
    for part in parts:
        if not isinstance(node, dict):
            return default
        node = node.get(part, default)
    return node


def update_secret(key: str, value: str) -> None:
    """Update a single key in .env (used by google_workspace.py when 'auto' IDs are created)."""
    env_key = key.upper()
    # set_key handles creating the file and updating existing keys atomically
    set_key(str(ENV_PATH), env_key, value)
    # Also update the live environment so the current process sees the new value
    os.environ[env_key] = value
