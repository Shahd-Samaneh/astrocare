"""Assistant tuning values.

They are read from config/thresholds.yaml (each with a source). Until Haya merges the keys
proposed in docs/proposals/support-contracts.md (A5), the same values are used as defaults.
"""
from __future__ import annotations

from typing import Any

from server.core.config import app_config, thresholds

# Pending proposal A5: these mirror the proposed thresholds.yaml entries exactly.
_PENDING_DEFAULTS: dict[str, Any] = {
    "assistant_timeout_sec": 20,
    "assistant_top_k": 4,
    "assistant_chunk_words": 500,
    "assistant_chunk_overlap_words": 50,
}


def setting(name: str) -> Any:
    entry = thresholds().get(name)
    if entry is not None and entry.value is not None:
        return entry.value
    return _PENDING_DEFAULTS[name]


def ollama_cfg() -> dict[str, str]:
    return app_config()["ollama"]
