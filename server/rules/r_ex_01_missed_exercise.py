"""R-EX-01 · Missed exercise (owner: Nadia)

The planned exercise session was skipped, or not logged at all, on
`exercise_missed_days` consecutive past days (default in contract: 2). It produces an
*info* alert that only says what is missing and offers a way back (pick an alternative).
It never judges the crew member and never suggests medication.

Notes for maintainers
  * Days with no planned session are neither missed nor done: they are skipped over.
  * Today is not counted: today's session can still be done.
  * A `partial` log (an alternative was done) counts as exercise done.
  * `RuleContext` has no exercise accessors yet, so this rule reads the plan and the logs
    through server.features.daily.exercise (proposal in docs/proposals/daily-contracts.md).
  * `exercise_missed_days` belongs in config/thresholds.yaml (Shahd adds it). Until the key
    exists the contract value below is used, so the rule keeps working.
  * `action` on a NextStep is the contract §1 proposal. NextStep ignores it today and will
    carry it as soon as the field is added to the contract, with no change here.
"""
from __future__ import annotations

from server.core.models import NextStep
from server.core.status import mission_clock
from server.features.daily.exercise import latest_log, load_plan_items

from .base import AlertDraft, Rule, RuleContext

CONTRACT_DEFAULT_DAYS = 2  # docs/daily-contract.md §3; only used while the threshold key is missing


def _limit(ctx: RuleContext) -> int:
    try:
        value = ctx.threshold("exercise_missed_days")
    except KeyError:
        value = None
    return int(value) if value else CONTRACT_DEFAULT_DAYS


class MissedExerciseRule(Rule):
    id = "R-EX-01"
    name = "Exercise skipped or not logged"
    sources = ["nasa-hrp-risks", "nasa-bone-risk"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        limit = _limit(ctx)
        today = mission_clock(ctx.now)[1]

        missed: list[tuple[int, str, dict | None]] = []  # (mission day, plan id, log or None)
        for plan in sorted((p for p in load_plan_items() if p["day"] < today), key=lambda p: -p["day"]):
            log = latest_log(plan["id"])
            if log is not None and log["status"] != "skipped":
                break  # done or partial: the streak ends here
            missed.append((plan["day"], plan["id"], log))
        if len(missed) < limit:
            return None

        days = sorted(d for d, _, _ in missed)
        skipped = [(d, log) for d, _, log in missed if log is not None]
        unlogged = [d for d, _, log in missed if log is None]
        day_list = ", ".join(str(d) for d in days)
        reasons = sorted({log["reason"] for _, log in skipped if log.get("reason")})

        changed = f"The planned exercise session was skipped or not logged on {len(days)} days in a row (mission days {day_list})."
        if reasons:
            changed += f" Reasons given: {', '.join(reasons)}."
        return AlertDraft(
            level="info",
            title=f"Exercise skipped or not logged for {len(days)} days",
            what_changed=changed,
            data_used=[log["id"] for _, log in skipped],
            missing=[f"Exercise log for mission day {d}" for d in sorted(unlogged)],
            possible_factors=[
                "A short night or tiredness (possible link, not confirmed)",
                "Equipment was not available",
                "A full schedule that day",
            ],
            next_steps=[NextStep(text="Pick an alternative", action={"label": "Open exercise", "route": "/daily#exercise"})],
            dedupe_key="missed-exercise",
        )
