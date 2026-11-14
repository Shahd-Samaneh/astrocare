"""Reports & comms API (owner: Noora).

Reports wait in the outbox (status 'queued') until a comm window opens.
Report items ("Add to report") are used by Monitoring, Daily and the Assistant.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field

from server.core import db
from server.core.config import app_config, iso, utcnow
from server.core.models import ApiModel, Report, ReportSection, ReportStatus
from server.core.status import build_status

from . import service

router = APIRouter(tags=["reports"])


# ---- report items (local type until Haya merges it into the contract) -------------
class ReportItem(ApiModel):
    id: str
    kind: Literal["alert", "cmo_question", "note"]
    ref_id: Optional[str] = None
    title: str
    text: str
    source_feature: Literal["monitoring", "daily", "assistant", "relax"]
    created_ts: str
    report_id: Optional[str] = None


class ReportItemIn(ApiModel):
    kind: Literal["alert", "cmo_question", "note"]
    ref_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=4000)
    source_feature: Literal["monitoring", "daily", "assistant", "relax"]


@router.post("/reports/items", status_code=201)
def add_item(body: ReportItemIn) -> ReportItem:
    item = service.add_report_item(body.kind, body.title, body.text, body.source_feature, body.ref_id)
    return ReportItem.model_validate(item)


@router.get("/reports/items")
def list_items(pending: bool = False) -> list[ReportItem]:
    return [ReportItem.model_validate(i) for i in service.list_report_items(pending_only=pending)]


@router.delete("/reports/items/{item_id}", status_code=204)
def delete_item(item_id: str) -> Response:
    if not service.delete_report_item(item_id):
        raise HTTPException(status_code=404, detail="Report item not found")
    return Response(status_code=204)


# ---- reports (unchanged for now; rebuilt in noura/reports) ------------------------
@router.get("/reports")
def list_reports(status: Optional[ReportStatus] = None) -> list[Report]:
    rows = db.query("reports", "status = ?", (status,), order_by="created_ts DESC") if status \
        else db.query("reports", order_by="created_ts DESC")
    return [Report.model_validate(r) for r in rows]


class ReportIn(ApiModel):
    sections: list[ReportSection] = Field(default_factory=list)
    status: ReportStatus = "draft"


@router.post("/reports", status_code=201)
def create_report(body: ReportIn) -> Report:
    rep = Report(id=db.new_id("rep"), created_ts=iso(utcnow()), status=body.status, sections=body.sections)
    db.insert("reports", rep.model_dump())
    db.log_action("crew", "create_report", rep.id)
    return rep


# ---- comms (unchanged for now; rebuilt in noura/comms) -----------------------------
class CommsStatus(ApiModel):
    local_mode: bool
    next_comm_window_ts: str
    signal_delay_sec: int
    last_sync_ts: str
    outbox: list[Report]


@router.get("/comms")
def comms() -> CommsStatus:
    s = build_status()
    outbox = [Report.model_validate(r) for r in db.query("reports", "status = 'queued'", order_by="created_ts")]
    return CommsStatus(
        local_mode=s.local_mode, next_comm_window_ts=s.next_comm_window_ts,
        signal_delay_sec=int(app_config()["comms"]["signal_delay_sec"]),
        last_sync_ts=s.last_sync_ts, outbox=outbox,
    )