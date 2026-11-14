"""Relax API: scenes, media and relaxation sessions (owner: Noura).

Media files live in /media (royalty-free, credited in media/CREDITS.md) and are served
locally by GET /api/relax/media/... (no remote URLs). Without media files, scenes still
work: the UI draws a local CSS gradient.

Stress is rated 1–10 (plan §11). The shared contract still says 1–5: see proposal N6.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import Field

from server.core import db
from server.core.config import ROOT, iso, utcnow
from server.core.models import ApiModel, AudioMode
from server.core.simulator import load_json

router = APIRouter(prefix="/relax", tags=["relax"])

MEDIA_DIR = ROOT / "media"
IMAGE_EXT = (".webp", ".jpg", ".jpeg", ".png")
AUDIO_EXT = (".mp3", ".ogg", ".m4a", ".wav")


# ---- media -----------------------------------------------------------------------------
def _media_url(rel: str) -> str:
    return f"/api/relax/media/{rel}"


def _find(folder: str, stem: str, exts: tuple[str, ...]) -> Optional[str]:
    for ext in exts:
        if (MEDIA_DIR / folder / f"{stem}{ext}").is_file():
            return _media_url(f"{folder}/{stem}{ext}")
    return None


def _music_track() -> Optional[str]:
    folder = MEDIA_DIR / "audio"
    if not folder.is_dir():
        return None
    tracks = sorted(p.name for p in folder.iterdir() if p.name.startswith("music") and p.suffix in AUDIO_EXT)
    return _media_url(f"audio/{tracks[0]}") if tracks else None


@router.get("/media/{path:path}", include_in_schema=False)
def media(path: str) -> FileResponse:
    target = (MEDIA_DIR / path).resolve()
    if MEDIA_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(target)


# ---- scenes ----------------------------------------------------------------------------
class SceneAudio(ApiModel):
    nature: Optional[str] = None
    music: Optional[str] = None


class Scene(ApiModel):
    id: str
    name: str
    description: str
    audio: list[AudioMode]           # modes offered for this scene
    image: Optional[str] = None      # local URL, or null -> the UI draws a gradient
    audio_files: SceneAudio          # local URLs; null = file not added yet


@router.get("/scenes")
def list_scenes() -> list[Scene]:
    music = _music_track()
    out = []
    for s in load_json("relax_scenes.json")["scenes"]:
        out.append(Scene(
            id=s["id"], name=s["name"], description=s["description"], audio=s["audio"],
            image=_find("scenes", s["id"], IMAGE_EXT),
            audio_files=SceneAudio(
                nature=_find("audio", f"{s['id']}-nature", AUDIO_EXT) if "nature" in s["audio"] else None,
                music=music if "music" in s["audio"] else None,
            ),
        ))
    return out


# ---- sessions (local type until Haya merges N6) ----------------------------------------
class RelaxSessionOut(ApiModel):
    id: str
    ts: str
    scene_id: str
    audio_mode: AudioMode
    duration_min: int
    stress_before: int = Field(ge=1, le=10)
    stress_after: Optional[int] = Field(default=None, ge=1, le=10)


class RelaxIn(ApiModel):
    scene_id: str = Field(min_length=1)
    audio_mode: AudioMode = "none"
    duration_min: Literal[3, 5, 10] = 5
    stress_before: int = Field(ge=1, le=10)
    stress_after: Optional[int] = Field(default=None, ge=1, le=10)


class RelaxPatch(ApiModel):
    stress_after: int = Field(ge=1, le=10)


@router.get("/sessions")
def list_sessions(n: int = Query(20, gt=0, le=200)) -> list[RelaxSessionOut]:
    return [RelaxSessionOut.model_validate(r) for r in db.query("relax_sessions", order_by="ts DESC", limit=n)]


@router.post("/sessions", status_code=201)
def add_session(body: RelaxIn) -> RelaxSessionOut:
    """Called when the session STARTS (stressAfter usually null), so a session that is
    interrupted (exit, closed tab) is already saved without the 'after' value."""
    s = RelaxSessionOut(id=db.new_id("relax"), ts=iso(utcnow()), **body.model_dump())
    db.insert("relax_sessions", s.model_dump())
    db.log_action("crew", "relax_session", s.id)
    return s


@router.patch("/sessions/{session_id}")
def finish_session(session_id: str, body: RelaxPatch) -> RelaxSessionOut:
    if not db.get("relax_sessions", session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    db.update("relax_sessions", session_id, {"stress_after": body.stress_after})
    return RelaxSessionOut.model_validate(db.get("relax_sessions", session_id))