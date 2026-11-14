"""Assistant API (owners: Marah + Noura).

Stub: returns a template answer. The real version will retrieve passages from
/references (embeddings via local Ollama `nomic-embed-text`) and answer with the
local `llama3.2:3b`. It must ALWAYS refuse medication / dosing questions and
send them to the CMO (crew medical officer) and flight surgeon instead.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import Field

from server.core import db
from server.core.config import app_config
from server.core.models import ApiModel

router = APIRouter(prefix="/assistant", tags=["assistant"])

DOSE_PATTERN = re.compile(r"\b(dose|dosage|doses|mg|milligram|mcg|how many (pills|tablets))\b", re.I)


class AskIn(ApiModel):
    question: str = Field(min_length=1, max_length=2000)


class Source(ApiModel):
    title: str
    path: str
    excerpt: Optional[str] = None


class AskOut(ApiModel):
    answer: str
    sources: list[Source] = []
    missing: list[str] = []
    refused: bool = False
    model: str


def _mentions_medicine(q: str) -> bool:
    if DOSE_PATTERN.search(q):
        return True
    ql = q.lower()
    for r in db.query("resources", "kind = 'medicine'"):
        first_word = r["name"].split(" ")[0].lower()  # "Ibuprofen tablets" -> "ibuprofen"
        if first_word in ql:
            return True
    return False


@router.post("/ask")
def ask(body: AskIn) -> AskOut:
    model = app_config()["ollama"]["chat_model"]
    if _mentions_medicine(body.question):
        return AskOut(
            answer=("I can't help with medicines or doses. Please contact the CMO, who can review it "
                    "with the flight surgeon during the next comm window."),
            refused=True, model=model,
        )
    return AskOut(
        answer=("(stub) This is a template answer. The real assistant will answer from the NASA "
                "reference texts in /references and list its sources."),
        sources=[], missing=["Reference texts not indexed yet"], refused=False, model=model,
    )


class AssistantInfo(ApiModel):
    ollama_url: str
    reachable: bool
    chat_model: str
    embed_model: str
    models_available: list[str] = []


@router.get("/info")
def info() -> AssistantInfo:
    cfg = app_config()["ollama"]
    reachable, models = False, []
    try:  # localhost only: never an internet call
        r = httpx.get(f"{cfg['url']}/api/tags", timeout=1.0)
        reachable = r.status_code == 200
        models = [m.get("name", "") for m in r.json().get("models", [])] if reachable else []
    except (httpx.HTTPError, ValueError):
        pass
    return AssistantInfo(
        ollama_url=cfg["url"], reachable=reachable, chat_model=cfg["chat_model"],
        embed_model=cfg["embed_model"], models_available=models,
    )
