"""Paths, YAML config, thresholds and time helpers.

Usage:
    from server.core.config import app_config, threshold, utcnow, iso
    stale = threshold("stale_minutes")          # -> 120
    meta = threshold_entry("co2_max")           # -> Threshold(value=None, unit=..., source=..., note=...)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SIM_DIR = DATA_DIR / "simulated"
REFERENCES_DIR = ROOT / "references"
DIST_DIR = ROOT / "app" / "dist"


def db_path() -> Path:
    """SQLite file. Override with ASTROCARE_DB_PATH (tests use a temp file)."""
    return Path(os.environ.get("ASTROCARE_DB_PATH", DATA_DIR / "astrocare.db"))


# ---- YAML ----------------------------------------------------------------
def _load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def app_config() -> dict[str, Any]:
    return _load_yaml("app.yaml")


@dataclass(frozen=True)
class Threshold:
    value: Any
    unit: str
    source: str
    note: str


@lru_cache
def thresholds() -> dict[str, Threshold]:
    raw = _load_yaml("thresholds.yaml")
    return {
        key: Threshold(
            value=entry.get("value"),
            unit=str(entry.get("unit", "")),
            source=str(entry.get("source", "")),
            note=str(entry.get("note", "")),
        )
        for key, entry in raw.items()
    }


# A source only counts as "real" when it cites a published reference, not a TODO/team/trial value.
_UNSOURCED_PREFIXES = ("todo", "team decision", "experimental", "trial")


def has_real_source(entry: Threshold) -> bool:
    source = entry.source.strip()
    return bool(source) and not source.lower().startswith(_UNSOURCED_PREFIXES)


def threshold_entry(name: str) -> Threshold:
    return thresholds()[name]


def threshold(name: str) -> Any:
    """The numeric value of a threshold (may be None when no source exists yet)."""
    return thresholds()[name].value


# ---- Time ----------------------------------------------------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    """ISO 8601 UTC with a trailing Z, e.g. 2026-11-11T10:00:00Z."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_met(met: str) -> tuple[int, int, int]:
    """'142:07:31' -> (142, 7, 31) as (days, hours, minutes)."""
    d, h, m = (int(x) for x in met.split(":"))
    return d, h, m


def format_met(total_seconds: float) -> str:
    total_min = int(total_seconds // 60)
    d, rem = divmod(total_min, 24 * 60)
    h, m = divmod(rem, 60)
    return f"{d:03d}:{h:02d}:{m:02d}"
