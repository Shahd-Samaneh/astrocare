"""Assistant API (owner: Marah).

POST /api/assistant/ask           { question } -> AssistantAnswer
POST /api/assistant/ask/stream    { question } -> NDJSON events: token* [reset] final (see service.py)
POST /api/assistant/warmup        load the local models into memory (best effort, background)
GET  /api/assistant/permissions   -> AssistantPermissions
PUT  /api/assistant/permissions   partial update, merged
GET  /api/assistant/info          model, size, RAM, measured latency and tokens/s

Answers come from references/ (indexed by `python -m server.features.assistant.ingest`)
and the user's own data, through the local llama3.2:3b on Ollama (localhost only).
Medication / dose / diagnosis questions are refused before the model is called.
"""
from __future__ import annotations

import json
import os
import sys
import threading

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from . import llm, store
from .models import AskIn, AssistantAnswer, AssistantInfo, AssistantPermissions, PermissionsPatch
from .permissions import get_permissions, set_permissions
from .service import answer_events, answer_question, prime_cache
from .settings import chat_model, ollama_cfg


def _warm_up_in_background() -> None:
    """Server startup: load the chat + embed models in a background thread (never blocks
    startup; warm_up ignores errors, so a missing Ollama is fine). Skipped under pytest or
    with ASTROCARE_NO_WARMUP=1."""
    if "pytest" in sys.modules or os.environ.get("ASTROCARE_NO_WARMUP") == "1":
        return
    threading.Thread(target=prime_cache, name="assistant-warmup", daemon=True).start()


# Router-level startup hook: runs next to main.py's lifespan, so core/main.py stays untouched.
router = APIRouter(prefix="/assistant", tags=["assistant"], on_startup=[_warm_up_in_background])


@router.post("/ask")
def ask(body: AskIn) -> AssistantAnswer:
    return answer_question(body.question)


@router.post("/ask/stream")
def ask_stream(body: AskIn) -> StreamingResponse:
    """Same flow as /ask, streamed: the first words show up as soon as the model writes them."""
    lines = (json.dumps(ev, ensure_ascii=False) + "\n" for ev in answer_events(body.question))
    return StreamingResponse(lines, media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/warmup", status_code=202)
def warmup(tasks: BackgroundTasks) -> dict:
    tasks.add_task(prime_cache)
    return {"ok": True}


@router.get("/permissions")
def read_permissions() -> AssistantPermissions:
    return AssistantPermissions.model_validate(get_permissions())


@router.put("/permissions")
def update_permissions(body: PermissionsPatch) -> AssistantPermissions:
    return AssistantPermissions.model_validate(set_permissions(body.model_dump(exclude_none=True)))


@router.get("/info")
def info() -> AssistantInfo:
    cfg = ollama_cfg()
    reachable, models, size, ram = False, [], None, None
    try:  # localhost only: never an internet call
        tags = llm.tags()
        reachable = True
        models = [m.get("name", "") for m in tags]
        model = chat_model()
        chat = next((m for m in tags if m.get("name") in (model, f"{model}:latest")), None)
        size = chat.get("size") if chat else None
        loaded = next((m for m in llm.running() if m.get("name") == (chat or {}).get("name")), None)
        ram = loaded.get("size") if loaded else None  # memory used by the loaded chat model
    except Exception:  # noqa: BLE001  Ollama off: report unreachable
        pass

    # measured from our own log: only real model answers count
    current = chat_model()
    llm_rows = [r for r in store.log_rows(200) if r["mode"] == "llm" and r.get("model") in (None, current)]
    avg_latency = round(sum(r["latency_ms"] for r in llm_rows) / len(llm_rows), 1) if llm_rows else None
    timed = [r for r in llm_rows if r.get("eval_count") and r.get("eval_duration_ns")]
    first = [r["first_token_ms"] for r in llm_rows if r.get("first_token_ms")]
    avg_first = round(sum(first) / len(first), 1) if first else None
    tps = (round(sum(r["eval_count"] for r in timed) / (sum(r["eval_duration_ns"] for r in timed) / 1e9), 1)
           if timed else None)

    return AssistantInfo(
        ollama_url=cfg["url"], reachable=reachable, chat_model=chat_model(), embed_model=cfg["embed_model"],
        models_available=models, model_size_bytes=size, ram_bytes=ram, avg_latency_ms=avg_latency, avg_first_token_ms=avg_first,
        tokens_per_sec=tps, answers_logged=len(store.log_rows(10_000)), chunks_indexed=store.chunk_count(),
    )
