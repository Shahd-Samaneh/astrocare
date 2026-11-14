"""Reports & comms API (owners: Marah + Noura).

Reports wait in the outbox (status 'queued') until a comm window opens.
PDF export will use ReportLab (write files to data/reports/, set file_path).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import Field

from server.core import db
from server.core.config import app_config, iso, utcnow
from server.core.models import ApiModel, Report, ReportSection, ReportStatus
from server.core.status import build_status

router = APIRouter(tags=["reports"])


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
