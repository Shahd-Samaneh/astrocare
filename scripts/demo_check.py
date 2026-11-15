"""Pre-demo check for the assistant: one line per check, ✅ or ❌, with timings.

    node scripts/py.mjs scripts/demo_check.py          (any OS, uses the project's .venv)
    .venv\\Scripts\\python scripts\\demo_check.py        (Windows, same thing without node)
    .venv/bin/python scripts/demo_check.py             (macOS / Linux)

Checks, in order:
  1. Ollama answers on localhost
  2. the chat model and the embed model are both pulled
  3. assistant_chunks is not empty (if it is, the references are indexed now)
  4. the prompt cache is primed (chat model loaded with the fixed system prompt + your data)
  5. an alert question is answered from the alert, without the model ("alert" mode)
  6. a general question is answered by the local model ("llm" mode, not the template)

It never reseeds the database: run `npm run reseed` first so the demo data is fresh.
For the demo data itself (day 142, R-FAT-01, stale/missing vitals, outbox, permissions, media),
run scripts/demo_state.py as well.
Exit code 0 when every check passed, 1 otherwise.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ALERT_QUESTION = "Why did I get the alert?"
MODEL_QUESTION = "How can sleep loss affect my performance on the mission?"


@dataclass
class Check:
    name: str
    ok: bool
    ms: int
    detail: str = ""

    def line(self) -> str:
        mark = "✅" if self.ok else "❌"
        timing = f"{self.ms / 1000:.1f} s" if self.ms >= 100 else f"{self.ms} ms"
        return f"{mark} {self.name:<34} {timing:>8}" + (f"   {self.detail}" if self.detail else "")


def _timed(name: str, fn: Callable[[], tuple[bool, str]]) -> Check:
    t0 = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001  any failure is a ❌, never a crash
        ok, detail = False, f"{type(e).__name__}: {e}"
    return Check(name, ok, int((time.perf_counter() - t0) * 1000), detail)


def _has_model(names: list[str], wanted: str) -> bool:
    """'nomic-embed-text' matches 'nomic-embed-text:latest'; 'llama3.2:3b' must match exactly."""
    return any(n == wanted or n == f"{wanted}:latest" for n in names)


def run_checks(log: Callable[[str], None] = print) -> list[Check]:
    from server.features.assistant import ingest, llm, service, store
    from server.features.assistant.settings import chat_model, ollama_cfg

    checks: list[Check] = []

    def add(c: Check) -> Check:
        checks.append(c)
        log(c.line())
        return c

    # 1. Ollama reachable
    names: list[str] = []

    def reach() -> tuple[bool, str]:
        nonlocal names
        names = [m.get("name", "") for m in llm.tags(timeout=3.0)]
        return True, ollama_cfg()["url"]

    reachable = add(_timed("Ollama reachable", reach)).ok

    # 2. both models pulled
    chat, embed = chat_model(), ollama_cfg()["embed_model"]

    def models() -> tuple[bool, str]:
        if not reachable:
            return False, "skipped: Ollama is not reachable"
        lost = [m for m in (chat, embed) if not _has_model(names, m)]
        if lost:
            return False, "missing: " + ", ".join(lost) + "  (run: ollama pull " + " && ollama pull ".join(lost) + ")"
        return True, f"{chat} + {embed}"

    add(_timed("Chat + embed models present", models))

    # 3. reference chunks indexed (index them now if the table is empty)
    def chunks() -> tuple[bool, str]:
        n = store.chunk_count()
        if n:
            return True, f"{n} chunks"
        if not reachable:
            return False, "0 chunks, and Ollama is needed to index them"
        stats = ingest.ingest()
        n = store.chunk_count()
        return n > 0, f"was empty: indexed {stats['sources']} sources, {n} chunks"

    add(_timed("Reference chunks indexed", chunks))

    # 4. prompt cache primed
    add(_timed("Prompt cache primed", lambda: (service.prime_cache(), "" if reachable else "Ollama is not reachable")))

    # 5. alert question: built from the alert, no model
    def alert_q() -> tuple[bool, str]:
        a = service.answer_question(ALERT_QUESTION)
        if a.mode != "alert":
            return False, f"mode {a.mode!r}, expected 'alert'"
        if not a.alert_rule_id:
            return False, "no open alert in the data (did you run npm run reseed?)"
        return True, f"explains {a.alert_rule_id}, {len(a.sources)} source(s)"

    add(_timed("Alert question", alert_q))

    # 6. general question: the local model answers (not the template)
    def model_q() -> tuple[bool, str]:
        a = service.answer_question(MODEL_QUESTION)
        if a.mode != "llm":
            return False, f"mode {a.mode!r}: {a.note or 'the model did not answer'}"
        return True, f"{len(a.answer.split())} words, {len(a.sources)} source(s)" + (f"; {a.note}" if a.note else "")

    add(_timed("Model question", model_q))
    return checks


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles: print ✅ / ❌ instead of crashing
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    print("Assistant demo check. Reminder: run `npm run reseed` first (this script does not reseed).\n")
    t0 = time.perf_counter()
    checks = run_checks()
    failed = [c for c in checks if not c.ok]
    total = time.perf_counter() - t0
    print()
    if failed:
        print(f"❌ {len(failed)} of {len(checks)} checks failed ({total:.1f} s): " + ", ".join(c.name for c in failed))
        return 1
    print(f"✅ All {len(checks)} checks passed ({total:.1f} s). Ready for the demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
