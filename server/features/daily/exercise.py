"""Exercise API (owner: Nadia). Contract: docs/daily-contract.md §2.

    GET  /api/exercise/plan?day=                   -> plan items with equipment + status resolved
    GET  /api/exercise/alternatives?planId=&reason= -> { alternatives: [...ranked], message? }
    POST /api/exercise/log                          -> ExerciseLog, then runs the rule engine

Other modules call `exercise_summary(days)`.

Plan items come from data/simulated/exercise_plan.json (an EXAMPLE plan, not a prescription).
The JSON is read directly because the `exercise_plans` table has no `intensity` column and
its `alternatives` column was typed as objects, while the plan stores alternative item ids
(see docs/proposals/daily-contracts.md). Equipment comes from the `resources` table, read
read-only, the same source the monitoring feature uses for /api/resources.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import ApiModel, ExerciseLog, ExerciseReason, ExerciseStatus
from server.core.simulator import load_json
from server.core.status import mission_clock
from server.rules.engine import run_rules

router = APIRouter(tags=["daily"])

INTENSITY_RANK = {"light": 0, "moderate": 1, "hard": 2}
# Resource statuses that mean "can't use it now". `low` still works (there is some left).
# `maintenance` / `disconnected` don't exist in ResourceStatus yet; they are accepted so the
# check keeps working if the resources contract grows them (see the proposal).
UNAVAILABLE_STATUSES = {"out_of_stock", "expired", "maintenance", "disconnected"}
STATUS_LABELS = {"available": "available", "low": "low stock"}


# ---- plan data ------------------------------------------------------------------
@lru_cache
def _all_items() -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in load_json("exercise_plan.json")["plans"]}


def load_plan_items() -> list[dict[str, Any]]:
    """Scheduled items (those with a mission day), ordered by day."""
    return sorted((p for p in _all_items().values() if p.get("day") is not None), key=lambda p: p["day"])


def get_item(item_id: str) -> Optional[dict[str, Any]]:
    return _all_items().get(item_id)


def plan_for_day(day: int) -> Optional[dict[str, Any]]:
    return next((p for p in load_plan_items() if p["day"] == day), None)


# ---- equipment ---------------------------------------------------------------------
def equipment_info(equipment_id: Optional[str]) -> Optional[dict[str, Any]]:
    """{id, name, status} from the resources table, or None when the item needs no equipment."""
    if not equipment_id:
        return None
    row = db.get("resources", equipment_id)
    if not row:
        return {"id": equipment_id, "name": equipment_id, "status": "unknown"}
    return {"id": row["id"], "name": row["name"], "status": row["status"]}


def is_usable(equipment: Optional[dict[str, Any]]) -> bool:
    return equipment is None or (equipment["status"] not in UNAVAILABLE_STATUSES and equipment["status"] != "unknown")


def latest_log(plan_id: str) -> Optional[dict[str, Any]]:
    rows = db.query("exercise_logs", "plan_id = ?", (plan_id,), order_by="ts DESC, rowid DESC", limit=1)
    return ExerciseLog.model_validate(rows[0]).model_dump(by_alias=True) if rows else None


def resolve_item(item: dict[str, Any], *, with_log: bool = True) -> dict[str, Any]:
    eq = equipment_info(item.get("equipmentId"))
    out = {
        "id": item["id"],
        "day": item.get("day"),
        "type": item["type"],
        "durationMin": item["durationMin"],
        "intensity": item["intensity"],
        "equipmentId": item.get("equipmentId"),
        "equipment": eq,
        "equipmentStatus": eq["status"] if eq else None,
        "available": is_usable(eq),
        "alternatives": list(item.get("alternatives", [])),
    }
    if with_log:
        log = latest_log(item["id"])
        alt = get_item(log["alternativeId"]) if log and log.get("alternativeId") else None
        if log and alt:
            log["alternativeType"] = alt["type"]  # extra: lets the UI say what was done instead
        out["log"] = log
    return out


# ---- alternatives ---------------------------------------------------------------------
def _why(plan: dict[str, Any], alt: dict[str, Any], eq: Optional[dict[str, Any]]) -> list[str]:
    reasons = []
    if INTENSITY_RANK[alt["intensity"]] < INTENSITY_RANK[plan["intensity"]]:
        reasons.append("Lighter")
    if alt["durationMin"] < plan["durationMin"]:
        reasons.append("Shorter")
    if eq is None:
        reasons.append("No equipment needed")
    else:
        reasons.append(f"Uses {eq['name']}, {STATUS_LABELS.get(eq['status'], eq['status'])}")
    return reasons


def rank_alternatives(plan: dict[str, Any], reason: Optional[str]) -> dict[str, Any]:
    """Usable alternatives for `plan`, ordered for `reason`. Pure apart from the equipment lookup."""
    plan_eq = equipment_info(plan.get("equipmentId"))
    candidates = []
    for alt_id in plan.get("alternatives", []):
        alt = get_item(alt_id)
        if not alt:
            continue
        eq = equipment_info(alt.get("equipmentId"))
        if not is_usable(eq):
            continue  # maintenance / disconnected / out of stock
        if reason == "equipment" and plan_eq and alt.get("equipmentId") == plan_eq["id"]:
            continue  # the same (broken) equipment
        candidates.append((alt, eq))

    if reason in ("fatigue", "pain"):  # lower intensity first, then shorter
        candidates.sort(key=lambda c: (INTENSITY_RANK[c[0]["intensity"]], c[0]["durationMin"]))
    elif reason == "time":  # shorter first, then lower intensity
        candidates.sort(key=lambda c: (c[0]["durationMin"], INTENSITY_RANK[c[0]["intensity"]]))
    # reason == "equipment" or none: keep the order the plan lists them in

    alternatives = [
        {
            "id": a["id"], "type": a["type"], "durationMin": a["durationMin"], "intensity": a["intensity"],
            "equipmentId": a.get("equipmentId"), "equipment": eq, "equipmentStatus": eq["status"] if eq else None,
            "why": _why(plan, a, eq),
        }
        for a, eq in candidates
    ]
    out: dict[str, Any] = {"alternatives": alternatives}
    if not alternatives:
        what = f"without {plan_eq['name']}" if plan_eq and (reason == "equipment" or not is_usable(plan_eq)) else "right now"
        out["message"] = f"No alternative available {what}. Try rescheduling."
    return out


# ---- endpoints -----------------------------------------------------------------------------
@router.get("/exercise/plan")
def exercise_plan(day: Optional[int] = Query(None, ge=0)) -> list[dict]:
    items = load_plan_items()
    if day is not None:
        items = [p for p in items if p["day"] == day]
    return [resolve_item(p) for p in items]


@router.get("/exercise/alternatives")
def exercise_alternatives(
    plan_id: str = Query(..., alias="planId"), reason: Optional[ExerciseReason] = None,
) -> dict:
    plan = get_item(plan_id)
    if not plan or plan.get("day") is None:
        raise HTTPException(404, "Exercise plan item not found.")
    return rank_alternatives(plan, reason)


class ExerciseLogIn(ApiModel):
    plan_id: str
    status: ExerciseStatus
    reason: Optional[ExerciseReason] = None
    alternative_id: Optional[str] = None


def _check_log(body: ExerciseLogIn, plan: dict[str, Any]) -> None:
    if body.status == "done":
        if body.reason or body.alternative_id:
            raise HTTPException(422, "A completed session has no reason or alternative.")
    elif body.status == "skipped":
        if not body.reason:
            raise HTTPException(422, "Say why the session was skipped (pain, fatigue, equipment or time).")
        if body.alternative_id:
            raise HTTPException(422, "A skipped session has no alternative. Log it as partial instead.")
    else:  # partial = the crew did an alternative instead
        if not body.alternative_id:
            raise HTTPException(422, "A partial session needs the alternative that was done.")
        if not body.reason:
            raise HTTPException(422, "Say why the original session was changed.")
        if body.alternative_id not in plan.get("alternatives", []):
            raise HTTPException(422, "That alternative doesn't belong to this plan item.")
        alt = get_item(body.alternative_id)
        eq = equipment_info(alt.get("equipmentId")) if alt else None
        if not is_usable(eq):
            raise HTTPException(422, f"{eq['name']} is not available right now.")


@router.post("/exercise/log", status_code=201)
def log_exercise(body: ExerciseLogIn) -> ExerciseLog:
    plan = get_item(body.plan_id)
    if not plan or plan.get("day") is None:
        raise HTTPException(404, "Exercise plan item not found.")
    _check_log(body, plan)
    entry = ExerciseLog(
        id=db.new_id("exl"), plan_id=body.plan_id, ts=iso(utcnow()), status=body.status,
        reason=body.reason, alternative_id=body.alternative_id,
    )
    db.insert("exercise_logs", entry.model_dump())
    db.log_action("crew", f"exercise_{entry.status}", entry.id)
    run_rules()
    return entry


# ---- service function --------------------------------------------------------------------------
def exercise_summary(days: int = 7) -> dict[str, Any]:
    """Planned today, plus done / partial / skipped / not-logged over the last `days` mission days.

    `partial` = an alternative was done instead. `skipReasons` counts the reason on every
    skipped or partial log. `notLogged` only counts past days (today can still be done).
    """
    today = mission_clock()[1]
    first = today - days + 1
    counts = {"done": 0, "partial": 0, "skipped": 0, "notLogged": 0}
    reasons: dict[str, int] = {}
    for item in load_plan_items():
        if not first <= item["day"] <= today:
            continue
        log = latest_log(item["id"])
        if log is None:
            if item["day"] < today:
                counts["notLogged"] += 1
            continue
        counts[log["status"]] += 1
        if log["status"] in ("skipped", "partial") and log.get("reason"):
            reasons[log["reason"]] = reasons.get(log["reason"], 0) + 1
    planned = plan_for_day(today)
    today_log = latest_log(planned["id"]) if planned else None
    return {
        "missionDay": today,
        "windowDays": days,
        "plannedToday": (
            {k: planned[k] for k in ("id", "type", "durationMin", "intensity", "equipmentId")} if planned else None
        ),
        "loggedToday": today_log["status"] if today_log else None,
        **counts,
        "skipReasons": reasons,
        "label": "Example plan (simulated)",
    }
