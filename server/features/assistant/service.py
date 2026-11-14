"""The /ask flow, as a stream of events (answer_events) or one final answer (answer_question).

1. safety filter (before the model)  -> fixed refusal, nothing sent to Ollama
2. alert question ("why did I get the alert?", a rule id) -> built from the alert (mode "alert"), no model
   "my data" question ("last 7 days", "بياناتي")          -> built from the fixed facts (mode "data"), no model
3. user context (permissions, no notePrivate) + top-k reference chunks
4. local model, streamed token by token; no first token within the first-token timeout -> 5
   an answer left empty by post-processing -> "This isn't in the on-board references or your data."
5. template fallback from the most important open alert (the reason goes in `note`, not in `missing`)
6. every answer is logged to assistant_log

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
from .direct import alert_answer, data_answer, is_alert_question
from .fallback import answer_steps, build_fallback, dedupe, fallback_note
from .models import AssistantAnswer, AssistantSource
from .prompt import CITE_ANY, SYSTEM_PROMPT, build_prompt, is_data_question, parse_answer, user_data_prefix
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


_NOT_FOUND = {
    "en": "This isn't in the on-board references or your data.",
    "ar": "هاي المعلومة مش موجودة بالمراجع اللي على المركبة ولا ببياناتك.",
}
_QUESTION_LEAD = re.compile(
    r"^\s*(?:(?:what|who|where|when|which|how|why)(?:'s)?(?:\s+(?:is|are|was|were|does|do|did|much|many|long|about))?"
    r"|(?:can|could|do|does|is|are)\s+you\s+(?:tell me|explain)(?:\s+about)?|tell me about|explain)\s+",
    re.I,
)
_QUESTION_LEAD_AR = re.compile(r"^\s*(?:شو|ايش|إيش|ما هي|ما هو|ما|ماذا|كم|وين|أين|متى|ليش|لماذا|كيف|قديش)\s+")


def question_topic(question: str) -> str:
    """'What is the temperature on Mars?' -> 'the temperature on Mars' (the MISSING item)."""
    q = question.strip().rstrip("?؟!. ")
    t = _QUESTION_LEAD_AR.sub("", _QUESTION_LEAD.sub("", q, count=1), count=1).strip()
    return t or q


def is_empty_answer(text: str) -> bool:
    """Nothing left to read: no words once citations, bullets and punctuation are gone."""
    return not re.sub(r"[\s\-*•#>_.,;:!?؟()]+", "", CITE_ANY.sub("", text or ""))


# a MISSING item that is a notice or advice, not missing data
_NOT_DATA = re.compile(r"template|local model|incomplete|next steps?|قالب|الموديل|الخطوات", re.I)
_ADVICE = re.compile(r"^\s*(?:protect|repeat|rest|consult|talk to|ask|contact|try|avoid|keep|schedule|follow|get|go|"
                     r"take|drink|reduce|increase|log|record|do)\b", re.I)


def real_missing(items: list[str], ctx: dict) -> list[str]:
    """Only real missing data: no template / model notices, and no next steps (the model often
    copies the alert's next steps or its own advice into MISSING)."""
    steps = [" ".join(str(s).split()).casefold() for a in ctx.get("alerts") or [] for s in a.get("nextSteps") or []]
    out = []
    for item in items:
        key = " ".join(item.split()).casefold().rstrip(".")
        if _NOT_DATA.search(item) or _ADVICE.match(item):
            continue
        if any(key and (key in s or s.rstrip(".") in key) for s in steps if s):
            continue
        out.append(item)
    return out


def _answer_mentions_medicine(text: str, terms: set[str]) -> bool:
    return bool(_DOSE_IN_ANSWER.search(text)) or mentions_medicine_name(text, terms)


def _embed_for_check(texts: list[str]) -> list[list[float]]:
    """Embeddings for the weak-citation check (short timeout: the check is skipped on failure)."""
    return llm.embed(texts, timeout=10.0)


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
    citation_report: list[dict] = []
    out: AssistantAnswer

    reason = check_question(question, terms)
    if reason:
        out = _refusal(question, reason, t0)
    elif is_alert_question(question):  # built from the alert's own fields: no model, instant
        answer, sources, missing, rule_id, steps = alert_answer(question, arabic=arabic)
        out = AssistantAnswer(answer=answer, sources=sources, missing=missing, refused=False, mode="alert",
                              alert_rule_id=rule_id, next_steps=steps, latency_ms=_ms(t0))
    elif is_data_question(question):  # built from the fixed facts: no model, instant
        answer, sources, missing = data_answer(build_context(), arabic=arabic)
        out = AssistantAnswer(answer=answer, sources=sources, missing=missing, refused=False, mode="data",
                              latency_ms=_ms(t0))
    else:
        try:
            ctx = build_context()
            hits = retrieve(question)
            prompt = build_prompt(question, ctx, hits, arabic=arabic)
            # the first-token deadline counts from the question, so retrieval time is included
            remaining = max(first_timeout - (time.perf_counter() - t0), 1.0)
            full, shown, blocked = "", 0, False
            # Arabic answers are slower per token and drift more: shorter cap
            max_tokens = int(setting("assistant_max_arabic_tokens" if arabic else "assistant_max_answer_tokens"))
            for item in llm.chat_stream(prompt.system, prompt.user, model=model, first_token_timeout=remaining,
                                        max_total_sec=max_total_sec, max_tokens=max_tokens):
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
                parsed = parse_answer(result.text, prompt, arabic=arabic, embed_fn=_embed_for_check,
                                      min_similarity=float(setting("assistant_citation_min_similarity")))
                citation_report = parsed.citation_report
                # a cut-off answer can only have a cut-off MISSING line: don't trust its items
                missing = real_missing(parsed.missing, ctx) if result.complete else []
                note = None if result.complete else _INCOMPLETE["ar" if arabic else "en"]
                answer, sources = parsed.answer, parsed.sources
                if is_empty_answer(answer):  # everything was removed (or the model only wrote MISSING)
                    answer, sources = _NOT_FOUND["ar" if arabic else "en"], []
                    missing = [question_topic(question)]
                out = AssistantAnswer(
                    answer=answer,
                    sources=[AssistantSource(id=s.id, title=s.title, url=s.url) for s in sources],
                    missing=dedupe(missing), refused=False, mode="llm", note=note, latency_ms=_ms(t0),
                )
        except llm.OllamaError as e:  # Ollama off, error, or no first token in time
            reason = "slow" if isinstance(e, llm.FirstTokenTimeout) else "unavailable"
            alert = latest_alert()
            answer, sources, missing = build_fallback(alert, arabic=arabic, reason=reason)
            out = AssistantAnswer(answer=answer, sources=sources, missing=missing, refused=False,
                                  mode="fallback", note=fallback_note(reason, arabic=arabic),
                                  next_steps=answer_steps(alert, arabic=arabic), latency_ms=_ms(t0))

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
            "citationCheck": citation_report,  # cosine per (sentence, cited passage); dropped if kept=False
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
