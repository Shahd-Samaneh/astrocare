"""The /ask flow, as a stream of events (answer_events) or one final answer (answer_question).

1. safety filter (before the model)  -> fixed refusal, nothing sent to Ollama
2. user context (permissions, no notePrivate) + top-k reference chunks
3. local model, streamed token by token; no first token within the first-token timeout -> 4
4. template fallback from the latest alert
5. every answer is logged to assistant_log

Events (NDJSON lines on POST /api/assistant/ask/stream):
  {"type": "token", "text": "..."}     a piece of the answer (safe to show)
  {"type": "reset"}                    discard the tokens shown so far (the final answer replaces them)
  {"type": "final", "answer": {...AssistantAnswer}, "stats": {...}}   always the last event
"""
from __future__ import annotations

import re
import time
from typing import Any, Iterator

from . import llm, store
from .context import build_context, latest_alert
from .fallback import build_fallback
from .models import AssistantAnswer, AssistantSource
from .prompt import SYSTEM_PROMPT, build_prompt, ensure_data_coverage, parse_answer, user_data_prefix
from .retrieval import retrieve
from .safety import check_question, is_arabic, medicine_terms, mentions_medicine_name, refusal_text
from .settings import chat_model, setting

# Third guard, on the model's output: a dose amount or a medicine name never reaches the user.
_DOSE_IN_ANSWER = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|µg|milligrams?|micrograms?|ml|tablets?|pills?|capsules?)\b", re.I)
# Streamed text is held back by this many characters, so the guard sees a whole medicine name
# or dose ("200 mg") before any of it is sent. Longest names in the lists are < 20 characters.
HOLD_BACK_CHARS = 24
_MISSING_START = re.compile(r"(^|\n)[ \t*_>-]*MISSING", re.I)
_INCOMPLETE = {
    "en": "The local model stopped before finishing: this answer may be incomplete",
    "ar": "الموديل المحلي وقف قبل ما يخلّص: الجواب ممكن يكون ناقص",
}


def _answer_mentions_medicine(text: str, terms: set[str]) -> bool:
    return bool(_DOSE_IN_ANSWER.search(text)) or mentions_medicine_name(text, terms)


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _refusal(question: str, reason: str, t0: float) -> AssistantAnswer:
    return AssistantAnswer(answer=refusal_text(reason, question), sources=[], missing=[], refused=True,
                           refusal_reason=reason, mode="fallback", latency_ms=_ms(t0))


def _safe_prefix_end(text: str) -> int:
    """How much of the streamed text may be shown: never the MISSING line, never the last
    HOLD_BACK_CHARS characters, and only up to a whitespace (no half words)."""
    end = len(text)
    m = _MISSING_START.search(text)
    if m:
        end = m.start()
    end = min(end, len(text) - HOLD_BACK_CHARS)
    if end <= 0:
        return 0
    ws = max(text.rfind(" ", 0, end), text.rfind("\n", 0, end))
    return ws + 1 if ws >= 0 else 0


def answer_events(
    question: str,
    *,
    model: str | None = None,
    first_token_timeout: float | None = None,
    max_total_sec: float | None = None,
) -> Iterator[dict[str, Any]]:
    t0 = time.perf_counter()
    question = question.strip()
    arabic = is_arabic(question)
    terms = medicine_terms()
    model = model or chat_model()
    first_timeout = float(first_token_timeout if first_token_timeout is not None
                          else setting("assistant_first_token_timeout_sec"))
    result: llm.ChatResult | None = None
    out: AssistantAnswer

    reason = check_question(question, terms)
    if reason:
        out = _refusal(question, reason, t0)
    else:
        try:
            ctx = build_context()
            hits = retrieve(question)
            prompt = build_prompt(question, ctx, hits, arabic=arabic)
            # the first-token deadline counts from the question, so retrieval time is included
            remaining = max(first_timeout - (time.perf_counter() - t0), 1.0)
            full, shown, blocked = "", 0, False
            for item in llm.chat_stream(prompt.system, prompt.user, model=model,
                                        first_token_timeout=remaining, max_total_sec=max_total_sec):
                if isinstance(item, llm.ChatResult):
                    result = item
                    break
                full += item
                if _answer_mentions_medicine(full, terms):
                    blocked = True
                    break  # closing the generator closes the Ollama stream
                end = _safe_prefix_end(full)
                if end > shown:
                    yield {"type": "token", "text": full[shown:end]}
                    shown = end

            if blocked:
                if shown:
                    yield {"type": "reset"}
                out = _refusal(question, "medication", t0)
            else:
                assert result is not None
                parsed = ensure_data_coverage(parse_answer(result.text, prompt, arabic=arabic), prompt, ctx, question,
                                              arabic=arabic)
                missing = parsed.missing
                if not result.complete:
                    # a cut-off answer can only have a cut-off MISSING line: don't trust its items
                    missing = [_INCOMPLETE["ar" if arabic else "en"]]
                out = AssistantAnswer(
                    answer=parsed.answer,
                    sources=[AssistantSource(id=s.id, title=s.title, url=s.url) for s in parsed.sources],
                    missing=missing, refused=False, mode="llm", latency_ms=_ms(t0),
                )
        except llm.OllamaError:  # Ollama off, error, or no first token in time
            answer, sources, missing = build_fallback(latest_alert(), arabic=arabic)
            out = AssistantAnswer(answer=answer, sources=sources, missing=missing, refused=False,
                                  mode="fallback", latency_ms=_ms(t0))

    first_ms = result.first_token_ms if result and out.mode == "llm" else None
    store.log_answer(question, out.latency_ms, out.mode, out.refused, out.refusal_reason,
                     result.eval_count if result else None, result.eval_duration_ns if result else None,
                     first_ms, model if out.mode == "llm" else None)
    yield {
        "type": "final",
        "answer": out.model_dump(by_alias=True),
        "stats": {
            "model": model if out.mode == "llm" else None,
            "firstTokenMs": first_ms,
            "evalCount": result.eval_count if result else None,
            "evalDurationNs": result.eval_duration_ns if result else None,
            "promptEvalCount": result.prompt_eval_count if result else None,
            "promptEvalMs": result.prompt_eval_ms if result else None,
        },
    }


def answer_question(question: str, **kw: Any) -> AssistantAnswer:
    """Non-streaming: run the same flow and return only the final answer."""
    final: dict[str, Any] | None = None
    for ev in answer_events(question, **kw):
        if ev["type"] == "final":
            final = ev
    assert final is not None
    return AssistantAnswer.model_validate(final["answer"])


def prime_cache() -> bool:
    """Startup / page-open warm-up: load the embed model, then load the chat model with the
    exact fixed system prompt + current user-data block so Ollama caches that prefix.
    Never raises (Ollama off, DB not ready, ...): returns False instead."""
    try:
        llm.embed(["warm up"], timeout=300.0)
        ok = llm.prime(SYSTEM_PROMPT, user_data_prefix(build_context()))
    except Exception:  # noqa: BLE001  best effort only
        return False
    return ok
