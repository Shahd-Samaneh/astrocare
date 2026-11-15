"""Bone & muscle (owners: Haya + Wala). No sensor measures bone or muscle in flight.

Two things, both shared by GET /bone/estimate, the Today tile and the Bone & muscle page:
  * Exercise adherence this week: the countermeasure the crew controls. Read from the exercise
    plan + latest log per plan item (server/features/daily/exercise.py), the same data R-EX-01
    uses. A `partial` log (an alternative was done) counts as exercise done, as in R-EX-01.
  * An ILLUSTRATIVE bone-density estimate: months in flight × NASA's average loss per month
    (thresholds.yaml, references/nasa-bone-risk.txt). Not a measurement: bone density needs a
    DEXA scan on Earth. Without sourced values the estimate is unavailable (no fallback numbers).
No medication or supplement advice here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from server.core.config import has_real_source, thresholds
from server.core.models import ApiModel
from server.core.status import mission_clock
from server.features.daily.exercise import latest_log, load_plan_items

router = APIRouter(tags=["monitoring"])

DAYS_PER_MONTH = 365.25 / 12  # average calendar month, to turn mission days into months
_MIN_KEY, _MAX_KEY = "bone_loss_pct_per_month_min", "bone_loss_pct_per_month_max"

WHY = "Exercise is the main countermeasure for bone and muscle loss"
LABEL = "Illustrative, not a measurement"
NOTE = "Illustrative, not a measurement — bone density needs a DEXA scan on Earth."
SOURCE_SCOPE = ("NASA's range is an average from 4–6 month missions; NASA says more research is "
                "needed to know if the rate persists on longer missions.")


# ---- exercise adherence -------------------------------------------------------
def week_adherence(today: int) -> dict[str, int]:
    """Planned sessions on past days of this mission week (today excluded: it can still be done),
    with their latest log status. Unlogged past sessions count as not done."""
    counts = {"planned": 0, "done": 0, "partial": 0, "skipped": 0, "not_logged": 0}
    for plan in load_plan_items():
        if not today - 6 <= plan["day"] <= today - 1:
            continue
        counts["planned"] += 1
        log = latest_log(plan["id"])
        counts[log["status"] if log else "not_logged"] += 1
    return counts


def most_days_exercised(counts: dict[str, int]) -> bool:
    """Done or partial on more than half of the planned days."""
    return counts["planned"] > 0 and (counts["done"] + counts["partial"]) * 2 > counts["planned"]


# ---- illustrative estimate ------------------------------------------------------
class BoneEstimate(ApiModel):
    """GET /bone/estimate. Months and the % range are rounded to one decimal place."""

    available: bool
    mission_day: int
    months_in_flight: float
    loss_pct_per_month_min: Optional[float] = None
    loss_pct_per_month_max: Optional[float] = None
    estimated_loss_pct_min: Optional[float] = None
    estimated_loss_pct_max: Optional[float] = None
    source: Optional[str] = None
    label: str = LABEL
    note: str = NOTE
    source_scope: str = SOURCE_SCOPE
    why: str = WHY


def bone_estimate(mission_day: Optional[int] = None) -> BoneEstimate:
    day = max(mission_clock()[1] if mission_day is None else mission_day, 0)
    months = day / DAYS_PER_MONTH
    all_t = thresholds()
    lo_t, hi_t = all_t.get(_MIN_KEY), all_t.get(_MAX_KEY)
    base = BoneEstimate(available=False, mission_day=day, months_in_flight=round(months, 1))
    if any(t is None or t.value is None or not has_real_source(t) for t in (lo_t, hi_t)):
        return base
    lo, hi = float(lo_t.value), float(hi_t.value)
    return base.model_copy(update={
        "available": True,
        "loss_pct_per_month_min": lo, "loss_pct_per_month_max": hi,
        "estimated_loss_pct_min": round(months * lo, 1), "estimated_loss_pct_max": round(months * hi, 1),
        "source": lo_t.source,
    })


@router.get("/bone/estimate")
def get_bone_estimate() -> BoneEstimate:
    return bone_estimate()
