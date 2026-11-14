"""Relax API: scenes and relaxation sessions (owners: Marah + Noura)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import ApiModel, AudioMode, RelaxSession
from server.core.simulator import load_json

router = APIRouter(prefix="/relax", tags=["relax"])


class Scene(ApiModel):
    id: str
    name: str
    description: str
    audio: list[AudioMode]
    file: Optional[str] = None  # path under /media, served locally once added


@router.get("/scenes")
def list_scenes() -> list[Scene]:
    return [Scene.model_validate(s) for s in load_json("relax_scenes.json")["scenes"]]


class RelaxIn(RelaxSession):
    id: str = Field(default_factory=lambda: db.new_id("relax"))
    ts: str = Field(default_factory=lambda: iso(utcnow()))


@router.get("/sessions")
def list_sessions(n: int = Query(20, gt=0, le=200)) -> list[RelaxSession]:
    return [RelaxSession.model_validate(r) for r in db.query("relax_sessions", order_by="ts DESC", limit=n)]


@router.post("/sessions", status_code=201)
def add_session(body: RelaxIn) -> RelaxSession:
    s = RelaxSession.model_validate(body.model_dump())
    db.insert("relax_sessions", s.model_dump())
    db.log_action("crew", "relax_session", s.id)
    return s
