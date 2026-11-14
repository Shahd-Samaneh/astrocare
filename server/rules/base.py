"""Rule base class and the context every rule receives.

To add a rule: copy r_data_01_stale.py to r_<area>_<nn>_<name>.py, change id /
name / sources, implement evaluate(). The engine finds it automatically.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property

from server.core import db
from server.core.config import Threshold, iso, thresholds, utcnow
from server.core.models import (
    CabinReading, CheckIn, CognitiveTest, NextStep, Profile, Reading, Resource, Sensor,
    SleepSession,
)


@dataclass
class AlertDraft:
    """What a rule returns. The engine turns it into a stored `Alert`."""

    level: str  # 'info' | 'review' | 'urgent'
    title: str
    what_changed: str
    data_used: list[str] = field(default_factory=list)  # reading ids
    missing: list[str] = field(default_factory=list)
    possible_factors: list[str] = field(default_factory=list)
    next_steps: list[NextStep] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # defaults to Rule.sources
    # Same rule + same key while the previous alert is still open = no duplicate.
    dedupe_key: str = ""


class RuleContext:
    """Read-only access to everything a rule may need. Data is loaded lazily."""

    def __init__(self, now: datetime | None = None, astronaut_id: str | None = None):
        self.now = now or utcnow()
        self.astronaut_id = astronaut_id

    # -- thresholds -----------------------------------------------------------
    @cached_property
    def thresholds(self) -> dict[str, Threshold]:
        return thresholds()

    def threshold(self, name: str):
        return self.thresholds[name].value

    # -- vitals ---------------------------------------------------------------
    def readings(self, metric: str, hours: float | None = None) -> list[Reading]:
        """Readings of one metric, oldest first; optionally only the last `hours`."""
        where, params = "metric = ?", [metric]
        if hours is not None:
            where += " AND ts >= ?"
            params.append(iso(self.now - timedelta(hours=hours)))
        return [Reading.model_validate(r) for r in db.query("readings", where, tuple(params), order_by="ts")]

    def latest(self, metric: str) -> Reading | None:
        rows = db.query("readings", "metric = ? AND ts <= ?", (metric, iso(self.now)), order_by="ts DESC", limit=1)
        return Reading.model_validate(rows[0]) if rows else None

    def cabin(self, metric: str, hours: float | None = 24) -> list[CabinReading]:
        where, params = "metric = ?", [metric]
        if hours is not None:
            where += " AND ts >= ?"
            params.append(iso(self.now - timedelta(hours=hours)))
        return [CabinReading.model_validate(r) for r in db.query("cabin_readings", where, tuple(params), order_by="ts")]

    @cached_property
    def sensors(self) -> list[Sensor]:
        return [Sensor.model_validate(r) for r in db.query("sensors")]

    def sensor_for(self, metric: str) -> Sensor | None:
        return next((s for s in self.sensors if metric in s.metrics), None)

    # -- daily ----------------------------------------------------------------
    def sleep(self, nights: int = 7) -> list[SleepSession]:
        rows = db.query("sleep_sessions", order_by="start DESC", limit=nights)
        return [SleepSession.model_validate(r) for r in reversed(rows)]

    def tests(self, n: int = 7) -> list[CognitiveTest]:
        rows = db.query("cognitive_tests", order_by="ts DESC", limit=n)
        return [CognitiveTest.model_validate(r) for r in reversed(rows)]

    def checkins(self, n: int = 7) -> list[CheckIn]:
        rows = db.query("checkins", order_by="ts DESC", limit=n)
        return [CheckIn.model_validate(r) for r in reversed(rows)]

    # -- profile & resources ----------------------------------------------------
    @cached_property
    def profile(self) -> Profile | None:
        rows = db.query("profiles", limit=1)
        return Profile.model_validate(rows[0]) if rows else None

    @cached_property
    def resources(self) -> list[Resource]:
        return [Resource.model_validate(r) for r in db.query("resources")]


class Rule(ABC):
    """Base class for every rule. Subclasses set the class attributes below."""

    id: str = ""
    name: str = ""
    sources: list[str] = []  # where the logic / threshold comes from

    @abstractmethod
    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        """Return an AlertDraft if the rule fires, else None. Must not write to the DB."""
