# Owner: Shahd
"""Crew alerts API (CMO and Commander view of R-LOC-01 events). Everything is local.

    GET  /api/crew/emergencies                 open watches/emergencies + history, each with its timeline
    POST /api/crew/emergencies/{id}/respond    the crew member's "I'm OK"
    POST /api/crew/emergencies/{id}/ack        { role: 'cmo' | 'commander', note? }
    POST /api/crew/emergencies/{id}/resolve    { outcome, note }
    POST /api/crew/demo/loc                    demo only (config/app.yaml demo: true)
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import Field

from server.core.models import ApiModel

from . import demo, store

router = APIRouter(tags=["crew"])

EmergencyStatus = Literal["watch", "emergency", "resolved"]
Outcome = Literal["responded", "sensor_issue", "medical_event", "other"]
Role = Literal["cmo", "commander"]


# ---- local types (feature-owned, like api.attention; not in the shared contract) -------
class LocSignal(ApiModel):
    kind: Literal["hr_change", "chest_gap", "no_motion", "low_spo2"]
    label: str
    ts: str
    detail: str


class TimelineStep(ApiModel):
    ts: str
    step: str  # detected | check_shown | responded | no_response | escalated | report_queued | ack_cmo | ack_commander | resolved
    actor: str  # system | crew | cmo | commander
    text: str


class CrewEmergency(ApiModel):
    id: str
    alert_id: str
    astronaut_id: str
    crew_name: str
    status: EmergencyStatus
    # The alert itself stays level 'urgent' in the shared contract; this flag marks it as the
    # emergency class (Watch, "Are you OK?", escalation). See docs/loc-notes.md.
    alert_level: Literal["urgent"] = "urgent"
    emergency: bool = True
    detected_ts: str
    opened_ts: str
    deadline_ts: str
    responded_ts: Optional[str] = None
    escalated_ts: Optional[str] = None
    ack_cmo_ts: Optional[str] = None
    ack_commander_ts: Optional[str] = None
    acknowledged: bool = False
    resolved_ts: Optional[str] = None
    outcome: Optional[Outcome] = None
    note: Optional[str] = None
    signals: list[LocSignal] = []
    missing: list[str] = []
    timeline: list[TimelineStep] = []
    report_item_id: Optional[str] = None
    report_note: Optional[str] = None


class CrewEmergencies(ApiModel):
    server_ts: str
    demo: bool
    response_seconds: int
    open: list[CrewEmergency]
    history: list[CrewEmergency]


class AckIn(ApiModel):
    role: Role
    note: Optional[str] = Field(default=None, max_length=500)


class ResolveIn(ApiModel):
    outcome: Outcome
    note: str = Field(min_length=1, max_length=1000)
    role: Role = "cmo"


class DemoOut(ApiModel):
    alert_id: str
    emergency_id: Optional[str] = None


def _out(em: dict) -> CrewEmergency:
    return CrewEmergency.model_validate({**em, "acknowledged": bool(em.get("ack_cmo_ts") or em.get("ack_commander_ts"))})


def _call(fn, *args):
    try:
        return _out(fn(*args))
    except store.CrewError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e


@router.get("/crew/emergencies")
def list_emergencies() -> CrewEmergencies:
    d = store.listing(store.clock())
    return CrewEmergencies.model_validate({**d, "open": [_out(e) for e in d["open"]], "history": [_out(e) for e in d["history"]]})


@router.post("/crew/emergencies/{em_id}/respond")
def respond(em_id: str) -> CrewEmergency:
    return _call(store.respond, em_id, store.clock())


@router.post("/crew/emergencies/{em_id}/ack")
def ack(em_id: str, body: AckIn) -> CrewEmergency:
    return _call(store.ack, em_id, body.role, body.note, store.clock())


@router.post("/crew/emergencies/{em_id}/resolve")
def resolve(em_id: str, body: ResolveIn) -> CrewEmergency:
    if not body.note.strip():
        raise HTTPException(status_code=422, detail="A note is required")
    try:
        return _out(store.resolve(em_id, body.outcome, body.note, store.clock(), body.role))
    except store.CrewError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e


@router.post("/crew/demo/loc", status_code=201)
def demo_loc() -> DemoOut:
    if not store.demo_enabled():
        raise HTTPException(status_code=404, detail="Demo controls are off (config/app.yaml demo: false)")
    now = store.clock()
    alert_id = demo.trigger(now)
    if alert_id is None:
        raise HTTPException(
            status_code=409,
            detail="No new alert: a possible-LOC event for this crew member is still open or was just handled. Resolve it, or try again in a minute.",
        )
    em = next((e for e in store.listing(now)["open"] if e["alert_id"] == alert_id), None)
    return DemoOut(alert_id=alert_id, emergency_id=em["id"] if em else None)
