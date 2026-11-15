# Owner: Shahd
"""LOC thresholds: the `loc:` group of config/thresholds.yaml (same pattern as `daily:`).

The core loader is flat, so it sees `loc` as one group entry. We read the nested keys here.

    from server.features.crew.thresholds import loc_threshold
    loc_threshold("response_seconds")    # -> 30
"""
from __future__ import annotations

from typing import Any

from server.core.config import Threshold, _load_yaml


def loc_entries() -> dict[str, Threshold]:
    group = _load_yaml("thresholds.yaml").get("loc") or {}
    return {
        key: Threshold(
            value=entry.get("value"), unit=str(entry.get("unit", "")),
            source=str(entry.get("source", "")), note=str(entry.get("note", "")),
        )
        for key, entry in group.items()
        if isinstance(entry, dict)
    }


def loc_threshold(name: str) -> Any:
    return loc_entries()[name].value  # KeyError if missing: fail loudly
