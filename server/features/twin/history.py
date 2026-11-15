"""Time-bounded reads for the twin timeline (owner: Shahd).

`BoundedContext` is a RuleContext that only sees data stored at or before `now`, so an existing
rule (R-FAT-01, R-SLP-01, R-HR-01, ...) can be evaluated "as of the end of mission day N" without
seeing later data. Rules never write to the DB (base.Rule.evaluate), and nothing here does either:
the timeline replays the rule's condition, it does not create alerts.

Mission-day boundaries come from the shared mission clock (core/status.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

from server.core import db
from server.core.config import iso
from server.core.models import CabinReading, CheckIn, CognitiveTest, Reading, SleepSession
from server.core.status import mission_clock, mission_day_start
from server.rules.base import Rule, RuleContext


class BoundedContext(RuleContext):
    """RuleContext whose time-series reads stop at `self.now` (inclusive)."""

    def readings(self, metric: str, hours: float | None = None) -> list[Reading]:
        where, params = "metric = ? AND ts <= ?", [metric, iso(self.now)]
        if hours is not None:
            where += " AND ts >= ?"
            params.append(iso(self.now - timedelta(hours=hours)))
        return [Reading.model_validate(r) for r in db.query("readings", where, tuple(params), order_by="ts")]

    def cabin(self, metric: str, hours: float | None = 24) -> list[CabinReading]:
        where, params = "metric = ? AND ts <= ?", [metric, iso(self.now)]
        if hours is not None:
            where += " AND ts >= ?"
            params.append(iso(self.now - timedelta(hours=hours)))
        rows = db.query("cabin_readings", where, tuple(params), order_by="ts")
        return [CabinReading.model_validate(r) for r in rows]

    def sleep(self, nights: int = 7) -> list[SleepSession]:
        # A night is known once it has ended.
        rows = db.query("sleep_sessions", '"end" <= ?', (iso(self.now),), order_by="start DESC", limit=nights)
        return [SleepSession.model_validate(r) for r in reversed(rows)]

    def tests(self, n: int = 7) -> list[CognitiveTest]:
        rows = db.query("cognitive_tests", "ts <= ?", (iso(self.now),), order_by="ts DESC", limit=n)
        return [CognitiveTest.model_validate(r) for r in reversed(rows)]

    def checkins(self, n: int = 7) -> list[CheckIn]:
        rows = db.query("checkins", "ts <= ?", (iso(self.now),), order_by="ts DESC", limit=n)
        return [CheckIn.model_validate(r) for r in reversed(rows)]


def fires(rule: Rule, ctx: RuleContext) -> bool:
    """True when the rule's condition holds in `ctx`. A failing rule counts as 'not known'."""
    try:
        return rule.evaluate(ctx) is not None
    except Exception:  # noqa: BLE001 - one broken rule must not break the timeline
        return False


def draft_level(rule: Rule, ctx: RuleContext) -> str | None:
    try:
        d = rule.evaluate(ctx)
    except Exception:  # noqa: BLE001
        return None
    return d.level if d else None


def day_bounds(day: int, now: datetime) -> tuple[datetime, datetime]:
    """(start, as_of) of mission day `day`: as_of is the end of that day, or `now` for today."""
    today = mission_clock(now)[1]
    start = mission_day_start(now) - timedelta(days=today - day)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start, min(end, now)


@lru_cache(maxsize=None)
def rule(rule_id: str) -> Rule | None:
    """An existing rule instance by id (discovered the same way as the engine)."""
    from server.rules.engine import discover_rules

    return next((r for r in discover_rules() if r.id == rule_id), None)
