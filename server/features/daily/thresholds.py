# Owner: Shahd
"""Daily thresholds: the `daily:` section of config/thresholds.yaml.

The core loader (`server.core.config.thresholds()`) is flat, so it sees `daily` as
one group entry. We read the nested keys with the same YAML loader. If a key is
missing under `daily:`, we fall back to the top-level key of the same name (the
scaffold already had `sleep_short_hours`, `attention_slower_pct`, `pvt_lapse_ms`).

    from server.features.daily.thresholds import daily_threshold
    daily_threshold("pvt_lapse_ms")        # -> 500
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from server.core.config import Threshold, _load_yaml, thresholds

router = APIRouter()


def daily_entries() -> dict[str, Threshold]:
    group = _load_yaml("thresholds.yaml").get("daily") or {}
    return {
        key: Threshold(
            value=entry.get("value"), unit=str(entry.get("unit", "")),
            source=str(entry.get("source", "")), note=str(entry.get("note", "")),
        )
        for key, entry in group.items()
        if isinstance(entry, dict)
    }


def daily_threshold_entry(name: str) -> Threshold:
    entries = daily_entries()
    if name in entries:
        return entries[name]
    return thresholds()[name]  # KeyError if it exists nowhere: fail loudly


def daily_threshold(name: str) -> Any:
    return daily_threshold_entry(name).value


@router.get("/daily/thresholds")
def list_daily_thresholds() -> dict[str, dict[str, Any]]:
    """Every `daily:` threshold with its unit, source and note (charts draw the lines from here)."""
    return {k: {"value": t.value, "unit": t.unit, "source": t.source, "note": t.note} for k, t in daily_entries().items()}
