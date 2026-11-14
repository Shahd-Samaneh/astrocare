"""Thin client for the local Ollama server (localhost:11434 only, never the internet).

Every failure (Ollama off, model missing, timeout, bad JSON) raises OllamaError, so the
caller can switch to the template fallback.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterator, Union

import httpx

from .settings import chat_model, ollama_cfg, setting

# Keep both models loaded between questions (a cold load can take over a minute on CPU).
KEEP_ALIVE = "60m"


class OllamaError(RuntimeError):
    pass


class FirstTokenTimeout(OllamaError):
    """No token arrived before the first-token deadline."""


@dataclass
class ChatResult:
    text: str
    eval_count: int | None = None        # tokens generated
    eval_duration_ns: int | None = None  # time spent generating them
    first_token_ms: int | None = None    # from the start of chat_stream to the first token
    prompt_eval_count: int | None = None # prompt length in tokens (Ollama reports the full prompt even when cached)
    # prompt_eval_ms is the real reading time: it drops when Ollama reuses the cached prompt prefix
    prompt_eval_ms: int | None = None
    model: str | None = None
    complete: bool = True                # False: stopped early (stall or total cap); text is partial


def _url(path: str) -> str:
    return f"{ollama_cfg()['url'].rstrip('/')}{path}"


def embed(texts: list[str], *, timeout: float = 60.0) -> list[list[float]]:
    """Embed a batch of texts with the configured embed model (nomic-embed-text)."""
    if not texts:
        return []
    try:
        r = httpx.post(_url("/api/embed"), json={"model": ollama_cfg()["embed_model"], "input": texts, "keep_alive": KEEP_ALIVE}, timeout=timeout)
        r.raise_for_status()
        vecs = r.json()["embeddings"]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        raise OllamaError(f"embed failed: {e}") from e
    if len(vecs) != len(texts):
        raise OllamaError("embed returned the wrong number of vectors")
    return vecs


def _chat_payload(system: str, user: str, model: str, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "stream": stream,
        "keep_alive": KEEP_ALIVE,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0.1, "num_predict": int(setting("assistant_max_answer_tokens")),
                    "num_ctx": int(setting("assistant_num_ctx"))},
    }


StreamItem = Union[str, ChatResult]


def chat_stream(
    system: str,
    user: str,
    *,
    model: str | None = None,
    first_token_timeout: float | None = None,
    max_total_sec: float | None = None,
) -> Iterator[StreamItem]:
    """Stream one chat turn. Yields each token (str) as it arrives, then one final ChatResult.

    - No first token within `first_token_timeout` -> FirstTokenTimeout (caller falls back).
      The same value is the allowed gap between two tokens; a stall after the first token,
      or going past `max_total_sec`, ends the answer early with `complete=False`.
    """
    model = model or chat_model()
    first_timeout = float(first_token_timeout if first_token_timeout is not None else setting("assistant_first_token_timeout_sec"))
    total_cap = float(max_total_sec if max_total_sec is not None else setting("assistant_max_answer_sec"))
    t0 = time.perf_counter()
    parts: list[str] = []
    first_ms: int | None = None
    final: dict[str, Any] = {}
    complete = True
    # read timeout = max wait for the next chunk; the first chunk only comes with the first token
    timeout = httpx.Timeout(connect=3.0, read=first_timeout, write=10.0, pool=3.0)
    try:
        with httpx.stream("POST", _url("/api/chat"), json=_chat_payload(system, user, model, True), timeout=timeout) as r:
            if r.status_code != 200:
                r.read()
                raise OllamaError(f"chat failed: HTTP {r.status_code} {r.text[:200]}")
            for line in r.iter_lines():
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise OllamaError(f"chat failed: {d['error']}")
                tok = (d.get("message") or {}).get("content", "")
                if tok:
                    if first_ms is None:
                        first_ms = int((time.perf_counter() - t0) * 1000)
                    parts.append(tok)
                    yield tok
                if d.get("done"):
                    final = d
                    if d.get("done_reason") == "length":
                        complete = False  # hit the token cap: the answer may stop mid-sentence
                    break
                if time.perf_counter() - t0 > total_cap:
                    complete = False
                    break
    except httpx.TimeoutException as e:
        if first_ms is None:
            raise FirstTokenTimeout(f"no first token within {first_timeout:.0f} s") from e
        complete = False  # stalled mid-answer: keep what we have
    except (httpx.HTTPError, ValueError) as e:
        if first_ms is None:
            raise OllamaError(f"chat failed: {e}") from e
        complete = False
    text = "".join(parts).strip()
    if not text:
        raise OllamaError("chat returned an empty answer")
    yield ChatResult(text=text, eval_count=final.get("eval_count"), eval_duration_ns=final.get("eval_duration"),
                     prompt_eval_count=final.get("prompt_eval_count"),
                     prompt_eval_ms=int(final["prompt_eval_duration"] / 1e6) if final.get("prompt_eval_duration") else None,
                     first_token_ms=first_ms, model=model, complete=complete)


def chat(system: str, user: str, **kw: Any) -> ChatResult:
    """Non-streaming convenience wrapper around chat_stream."""
    result: ChatResult | None = None
    for item in chat_stream(system, user, **kw):
        if isinstance(item, ChatResult):
            result = item
    assert result is not None
    return result


def tags(timeout: float = 1.5) -> list[dict[str, Any]]:
    r = httpx.get(_url("/api/tags"), timeout=timeout)
    r.raise_for_status()
    return r.json().get("models", [])


def running(timeout: float = 1.5) -> list[dict[str, Any]]:
    """Models currently loaded in memory (/api/ps), with their RAM/VRAM size."""
    r = httpx.get(_url("/api/ps"), timeout=timeout)
    r.raise_for_status()
    return r.json().get("models", [])


def warm_up(model: str | None = None) -> None:
    """Load both models into memory without generating anything (best effort)."""
    cfg = ollama_cfg()
    try:
        httpx.post(_url("/api/embed"), json={"model": cfg["embed_model"], "input": ["warm up"], "keep_alive": KEEP_ALIVE}, timeout=300.0)
        httpx.post(_url("/api/generate"), json={"model": model or chat_model(), "keep_alive": KEEP_ALIVE}, timeout=300.0)
    except httpx.HTTPError:
        pass
