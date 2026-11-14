"""DEV ONLY: benchmark the 4 ready-made questions on one or more local models.

    node scripts/py.mjs -m server.features.assistant.bench llama3.2:3b llama3.2:1b

Runs the real /ask flow (filter, context, retrieval, streaming) with the timeouts lifted, so the
true times are measured. Each model is loaded first (load time reported separately) and
unloaded afterwards so the models don't compete for RAM. Writes a JSON report next to stdout.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

from . import llm
from .context import build_context
from .prompt import SYSTEM_PROMPT, user_data_prefix
from .service import answer_events
from .settings import ollama_cfg

QUESTIONS = [
    "Why did I get the alert?",
    "How can sleep loss affect my performance on the mission?",
    "What does my data from the last 7 days show?",
    "Can I take melatonin to sleep better?",
]


def _unload(model: str) -> None:
    try:
        httpx.post(f"{ollama_cfg()['url']}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    except httpx.HTTPError:
        pass


def run(model: str) -> dict:
    t = time.perf_counter()
    llm.warm_up(model)
    load_s = round(time.perf_counter() - t, 1)
    # same as the app at startup: cache the fixed system prompt + user-data block
    t = time.perf_counter()
    llm.prime(SYSTEM_PROMPT, user_data_prefix(build_context()), model=model)
    prime_s = round(time.perf_counter() - t, 1)
    rows = []
    for q in QUESTIONS:
        t0 = time.perf_counter()
        first_shown = None
        final = None
        for ev in answer_events(q, model=model, first_token_timeout=600, max_total_sec=600):
            if ev["type"] == "token" and first_shown is None:
                first_shown = time.perf_counter() - t0
            if ev["type"] == "final":
                final = ev
        total = time.perf_counter() - t0
        a, st = final["answer"], final["stats"]
        tps = (st["evalCount"] / (st["evalDurationNs"] / 1e9)) if st.get("evalCount") and st.get("evalDurationNs") else None
        rows.append({
            "question": q, "mode": a["mode"], "refused": a["refused"],
            "modelFirstTokenS": round(st["firstTokenMs"] / 1000, 1) if st.get("firstTokenMs") else None,
            "firstShownS": round(first_shown, 1) if first_shown else None,
            "totalS": round(total, 1), "tokensPerSec": round(tps, 1) if tps else None,
            "tokens": st.get("evalCount"),
            "promptTokensRead": st.get("promptEvalCount"), "promptReadS": round(st["promptEvalMs"] / 1000, 1) if st.get("promptEvalMs") else None,
            "answer": a["answer"], "sources": [s["title"] for s in a["sources"]], "missing": a["missing"],
        })
        print(f"[{model}] {q[:45]:45s} first={rows[-1]['firstShownS']}s total={rows[-1]['totalS']}s "
              f"tok/s={rows[-1]['tokensPerSec']} prompt_read={rows[-1]['promptTokensRead']}tok/{rows[-1]['promptReadS']}s mode={a['mode']} refused={a['refused']}", flush=True)
    return {"model": model, "loadS": load_s, "primeS": prime_s, "rows": rows}


def main(argv: list[str]) -> int:
    models = argv or ["llama3.2:3b"]
    for m in models:
        _unload(m)  # every model starts from the same (unloaded) state
    report = []
    for i, m in enumerate(models):
        report.append(run(m))
        if i < len(models) - 1:
            _unload(m)  # free RAM for the next model; the last one stays loaded for the app
    out = Path(__file__).resolve().parents[3] / "data" / "assistant_bench.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
