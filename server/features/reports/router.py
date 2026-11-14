"""Reports & comms API (owner: Noura).

Report items ("Add to report") are used by Monitoring, Daily and the Assistant.
A report is built from fixed sections, saved as PDF + JSON in data/reports/,
then waits in the outbox (queued) until a comm window opens (sent).
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import Field

from server.core import db
from server.core.models import ApiModel, Report, ReportStatus

from . import service

router = APIRouter(tags=["reports"])

SectionId = Literal[
    "summary", "alerts", "vitals", "cabin", "sleep", "attention",
    "exercise", "checkins", "relax", "items", "radiation",
]


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


# ---- reports -------------------------------------------------------------------------
class ReportOut(Report):
    """Contract Report + when it was sent (null until a comm window sends it)."""
    sent_ts: Optional[str] = None


def _out(row: dict, sent: dict[str, str]) -> ReportOut:
    return ReportOut.model_validate({**row, "sent_ts": sent.get(row["id"])})


@router.get("/reports")
def list_reports(status: Optional[ReportStatus] = None) -> list[ReportOut]:
    rows = db.query("reports", "status = ?", (status,), order_by="created_ts DESC") if status \
        else db.query("reports", order_by="created_ts DESC")
    sent = service.sent_ts_by_report()
    return [_out(r, sent) for r in rows]


class ReportIn(ApiModel):
    sections: list[SectionId] = Field(min_length=1)
    item_ids: Optional[list[str]] = None  # null = every pending item (only if 'items' is selected)


@router.post("/reports", status_code=201)
def create_report(body: ReportIn) -> ReportOut:
    row = service.create_report(list(body.sections), body.item_ids)
    return _out(row, {})


@router.get("/reports/{report_id}/file")
def report_file(report_id: str, format: Literal["pdf", "json"] = Query("pdf")) -> FileResponse:
    path = service.report_file(report_id, format)
    if path is None:
        raise HTTPException(status_code=404, detail="No file for this report")
    media = "application/pdf" if format == "pdf" else "application/json"
    return FileResponse(path, media_type=media, filename=f"astrocare-{report_id}.{format}",
                        content_disposition_type="inline")


@router.post("/reports/{report_id}/queue")
def queue_report(report_id: str) -> ReportOut:
    try:
        row = service.queue_report(report_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _out(row, service.sent_ts_by_report())


# ---- comms window ------------------------------------------------------------------
class CommsStatus(ApiModel):
    connected: bool
    simulated_window: bool
    next_window_ts: str
    window_duration_min: int
    queued_count: int
    signal_delay_sec: int
    last_window_ts: Optional[str] = None


class SimulatedWindow(ApiModel):
    window_id: str
    opened_ts: str
    sent_report_ids: list[str]


@router.get("/comms")
def comms() -> CommsStatus:
    return CommsStatus.model_validate(service.get_comms_status())


@router.post("/comms/simulate-window")
def simulate_window() -> SimulatedWindow:
    """Demo only: opens the comm window now and sends every queued report."""
    return SimulatedWindow.model_validate(service.simulate_window())