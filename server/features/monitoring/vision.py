"""Vision self-check (owners: Haya + Wala). There is no sensor for vision & fluid shift (SANS).

The crew member does two quick checks per eye:
  1. Near-vision card: lines of text in decreasing sizes (line 1 = largest). They pick the smallest
     line they can read comfortably at arm's length.
  2. Amsler grid: "Do any lines look wavy, blurred or missing?" (yes/no).

Each answer is one row in `vision_checks` (eye 'left' | 'right' | 'both').

Comparison with the baseline (shared by GET /vision/summary, the Today tile and rule R-VIS-01):
  * baseline for an eye = the earliest check that covers it (eye == that eye, or 'both');
    latest = the most recent check that covers it.
  * "lines changed": the smallest readable line moved `vision_line_drop_min` lines or more towards
    larger text (a lower line number). Thresholds are trial values (team decision).
  * "grid changed": the latest check reports wavy, blurred or missing lines.
This is a self-check to notice changes. It never diagnoses; changes go to the CMO for eye exams.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional, Union

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.config import REFERENCES_DIR, iso, parse_ts, threshold, utcnow
from server.core.models import ApiModel
from server.core.status import mission_clock

router = APIRouter(tags=["monitoring"])

NEAR_VISION_LINES = 10  # lines on the card (app/src/features/monitoring/pages/Vision.tsx)
Eye = Literal["left", "right", "both"]
VisionSource = Literal["self", "simulated"]
VisionStatus = Literal["stable", "review", "no_data"]

DISCLAIMER = "A self-check to notice changes. It does not diagnose. Changes go to the CMO for proper eye exams."
WHY = ("Living in weightlessness can slowly change the shape of the eye and the back of the eye, "
       "so a quick, repeatable check helps notice a change early and pass it on to the CMO.")
SOURCE_REF = "nasa-hrp-risks"
SAME_AS_BASELINE = "Same as baseline"


def _source_title() -> str:
    """Title line of references/nasa-hrp-risks.txt (never invented here)."""
    try:
        first = (REFERENCES_DIR / f"{SOURCE_REF}.txt").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return SOURCE_REF
    return first.removeprefix("title:").strip() or SOURCE_REF


class VisionCheck(ApiModel):
    id: str
    ts: str
    eye: Eye
    near_vision_smallest_line: int
    amsler_changed: bool
    notes: Optional[str] = None
    source: VisionSource = "self"


class VisionCheckIn(ApiModel):
    eye: Eye
    near_vision_smallest_line: int = Field(ge=1, le=NEAR_VISION_LINES)
    amsler_changed: bool
    notes: Optional[str] = Field(default=None, max_length=1000)
    ts: Optional[str] = None


class VisionEyeResult(ApiModel):
    """One eye compared with its baseline. lines_moved > 0 = smaller text read than at baseline."""

    eye: Literal["left", "right"]
    baseline: Optional[VisionCheck] = None
    latest: Optional[VisionCheck] = None
    lines_moved: Optional[int] = None
    lines_changed: bool = False
    grid_changed: bool = False


class VisionSummary(ApiModel):
    """Latest self-check vs baseline, for the Vision page, the Today tile and R-VIS-01.

    status: review = a change reported; no_data = no check in `due_days`; else stable.
    changes: one plain sentence per change ("Changed since baseline: …", "Grid changes reported …").
    """

    status: VisionStatus
    changed: bool
    due: bool
    result: str
    changes: list[str] = []
    eyes: list[VisionEyeResult] = []
    last_ts: Optional[str] = None
    last_mission_day: Optional[int] = None
    baseline_ts: Optional[str] = None
    baseline_mission_day: Optional[int] = None
    line_drop_min: int
    due_days: int
    lines_on_card: int = NEAR_VISION_LINES
    disclaimer: str = DISCLAIMER
    why: str = WHY
    source_ref: str = SOURCE_REF
    source_title: str = ""


def list_checks(n: Optional[int] = None, until: Optional[datetime] = None) -> list[VisionCheck]:
    """Checks newest first (optionally only those at or before `until`)."""
    where, params = ("ts <= ?", (iso(until),)) if until else ("", ())
    rows = db.query("vision_checks", where, params, order_by="ts DESC, id DESC", limit=n)
    return [VisionCheck.model_validate(r) for r in rows]


def _eye_label(eye: str) -> str:
    return f"{eye} eye"


def vision_summary(now: Optional[datetime] = None) -> VisionSummary:
    now = now or utcnow()
    drop_min = int(threshold("vision_line_drop_min"))
    due_days = int(threshold("vision_check_due_days"))
    checks = list(reversed(list_checks(until=now)))  # oldest first
    common = {"line_drop_min": drop_min, "due_days": due_days, "source_title": _source_title()}
    if not checks:
        return VisionSummary(status="no_data", changed=False, due=True, result="No self-check yet", **common)

    eyes: list[VisionEyeResult] = []
    changes: list[str] = []
    for eye in ("left", "right"):
        covering = [c for c in checks if c.eye in (eye, "both")]
        if not covering:
            eyes.append(VisionEyeResult(eye=eye))
            continue
        base, last = covering[0], covering[-1]
        moved = base.near_vision_smallest_line - last.near_vision_smallest_line
        res = VisionEyeResult(
            eye=eye, baseline=base, latest=last, lines_moved=moved,
            lines_changed=last.id != base.id and moved >= drop_min,
            grid_changed=last.amsler_changed,
        )
        eyes.append(res)
        if res.lines_changed:
            changes.append(
                f"Changed since baseline: smallest readable line moved from {base.near_vision_smallest_line} "
                f"to {last.near_vision_smallest_line} ({_eye_label(eye)})"
            )
        if res.grid_changed:
            changes.append(f"Grid changes reported ({_eye_label(eye)})")

    # One 'both' check counts for both eyes: say it once.
    if all(e.latest is not None and e.latest.eye == "both" for e in eyes):
        changes = list(dict.fromkeys(c.replace(" (left eye)", " (both eyes)").replace(" (right eye)", " (both eyes)")
                                     for c in changes))

    last_ts = checks[-1].ts
    base_ts = checks[0].ts
    changed = bool(changes)
    due = parse_ts(last_ts) < now - timedelta(days=due_days)
    status: VisionStatus = "review" if changed else ("no_data" if due else "stable")
    return VisionSummary(
        status=status, changed=changed, due=due,
        result="; ".join(changes) if changed else SAME_AS_BASELINE, changes=changes, eyes=eyes,
        last_ts=last_ts, last_mission_day=mission_clock(parse_ts(last_ts))[1],
        baseline_ts=base_ts, baseline_mission_day=mission_clock(parse_ts(base_ts))[1],
        **common,
    )


def body_system_tile(now: Optional[datetime] = None) -> tuple[VisionStatus, str, Optional[str]]:
    """(status, text, status_label) for the Today 'Vision & fluid shift' tile."""
    s = vision_summary(now)
    if s.last_mission_day is None:
        return "no_data", "No self-check yet", "Self-check due"
    text = f"Self-check · last mission day {s.last_mission_day}"
    if s.status == "review":
        return "review", text, "change reported"
    if s.status == "no_data":
        return "no_data", text, "Self-check due"
    return "stable", text, "no change vs baseline"


# ---- API ----------------------------------------------------------------------------
@router.get("/vision/checks")
def get_checks(n: int = Query(10, ge=1, le=200)) -> list[VisionCheck]:
    return list_checks(n)


def _insert(body: VisionCheckIn) -> VisionCheck:
    check = VisionCheck(
        id=db.new_id("vis"), ts=body.ts or iso(utcnow()), eye=body.eye,
        near_vision_smallest_line=body.near_vision_smallest_line, amsler_changed=body.amsler_changed,
        notes=(body.notes or "").strip() or None, source="self",
    )
    db.insert("vision_checks", check.model_dump())
    db.log_action("crew", "vision_check", check.id)
    return check


@router.post("/vision/checks", status_code=201)
def post_checks(body: Union[VisionCheckIn, list[VisionCheckIn]]) -> Union[VisionCheck, list[VisionCheck]]:
    """One check, or a list (left + right from one session). Rules run once, after all are saved,
    so R-VIS-01 sees the whole session."""
    from server.rules.engine import run_rules

    saved = [_insert(b) for b in body] if isinstance(body, list) else _insert(body)
    run_rules()
    return saved


@router.get("/vision/summary")
def get_summary() -> VisionSummary:
    return vision_summary()
