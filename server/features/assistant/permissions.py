"""Data permissions for the assistant and for reports (contracts §5).

Noura (reports) imports this read-only:
    from server.features.assistant.permissions import get_permissions
    if get_permissions()["report"]["checkins"]: ...
"""
from __future__ import annotations

import copy
from typing import Any

from . import store

DEFAULT_PERMISSIONS: dict[str, dict[str, bool]] = {
    "assistant": {"vitals": True, "sleep": True, "tests": True, "exercise": True, "checkins": False},
    "report": {"checkins": False},
}


def _merge(base: dict[str, dict[str, bool]], patch: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    """Overlay only known groups/keys with boolean values; ignore anything else."""
    out = copy.deepcopy(base)
    for group, keys in (patch or {}).items():
        if group not in out or not isinstance(keys, dict):
            continue
        for key, val in keys.items():
            if key in out[group] and isinstance(val, bool):
                out[group][key] = val
    return out


def get_permissions() -> dict[str, dict[str, bool]]:
    """Current permissions: the defaults overlaid with whatever was saved."""
    return _merge(DEFAULT_PERMISSIONS, store.load_permissions())


def set_permissions(patch: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Merge a (partial) update into the current permissions, save and return them."""
    new = _merge(get_permissions(), patch)
    store.save_permissions(new)
    return new
