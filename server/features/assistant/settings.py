"""Assistant tuning values and the chat model name.

Numbers are read from config/thresholds.yaml (each with a source). Until Haya merges the keys
proposed in docs/proposals/support-contracts.md (A5), the same values are used as defaults.
"""
from __future__ import annotations

import os
from typing import Any

from server.core.config import app_config, thresholds

DEFAULT_CHAT_MODEL = "llama3.2:3b"

# Pending proposal A5: these mirror the proposed thresholds.yaml entries exactly.
_PENDING_DEFAULTS: dict[str, Any] = {
    "assistant_first_token_timeout_sec": 20,
    "assistant_max_answer_sec": 90,
    "assistant_top_k": 4,
    "assistant_chunk_words": 500,
    "assistant_chunk_overlap_words": 50,
    "assistant_max_answer_tokens": 200,
    "assistant_num_ctx": 4096,
}


def setting(name: str) -> Any:
    entry = thresholds().get(name)
    if entry is not None and entry.value is not None:
        return entry.value
    return _PENDING_DEFAULTS[name]


def ollama_cfg() -> dict[str, str]:
    return app_config()["ollama"]


def chat_model() -> str:
    """Chat model: ASTROCARE_CHAT_MODEL env var > config/app.yaml ollama.chat_model > llama3.2:3b.

    e.g. on a low-RAM machine:  set ASTROCARE_CHAT_MODEL=llama3.2:1b  (then restart the API)
    """
    return (os.environ.get("ASTROCARE_CHAT_MODEL") or ollama_cfg().get("chat_model") or DEFAULT_CHAT_MODEL).strip()
