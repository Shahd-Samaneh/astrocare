"""Tests for R-CAB-01 (cabin CO₂ above the 1-hour average limit).

co2_max is 3 mmHg, co2_avg_window_minutes is 60. Each test isolates the co2
cabin readings (deletes the seeded ones, inserts a controlled set, restores
afterwards) so the windowed average is deterministic.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

from server.core import db
from server.core.config import iso, utcnow
from server.rules.base import RuleContext
from server.rules.r_cab_01_co2 import CabinCo2Rule


def _co2(value: float, minutes_ago: int) -> dict:
    return {
        "id": db.new_id("c-co2test"), "metric": "co2", "value": value, "unit": "mmHg",
        "ts": iso(utcnow() - timedelta(minutes=minutes_ago)), "source": "simulated",
    }


@contextmanager
def _only_co2(readings: list[dict]):
    """Replace all co2 cabin readings with `readings` for the test."""
    from server.core.db import connect

    saved = db.query("cabin_readings", "metric = 'co2'")
    with connect() as conn:
        conn.execute("DELETE FROM cabin_readings WHERE metric = 'co2'")
    if readings:
        db.insert_many("cabin_readings", readings)
    try:
        yield
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM cabin_readings WHERE metric = 'co2'")
        if saved:
            db.insert_many("cabin_readings", saved)


def test_average_above_limit_fires(client):
    with _only_co2([_co2(4.0, 10), _co2(5.0, 20)]):  # avg 4.5 > 3
        draft = CabinCo2Rule().evaluate(RuleContext())
        assert draft is not None
        assert draft.level == "review"
        assert draft.dedupe_key == "cab-co2-high"
        assert len(draft.data_used) >= 2
        assert any(s.locked_for_cmo for s in draft.next_steps)  # CMO step for symptoms
        assert "cause" not in draft.what_changed.lower()


def test_average_below_limit_does_not_fire(client):
    with _only_co2([_co2(2.0, 10), _co2(2.0, 20)]):  # avg 2.0 < 3
        assert CabinCo2Rule().evaluate(RuleContext()) is None


def test_one_high_reading_but_average_below_does_not_fire(client):
    # Nine low readings and one spike: the windowed average stays below the limit.
    readings = [_co2(1.0, m) for m in range(5, 50, 5)] + [_co2(9.0, 1)]  # avg = (9*1 + 9)/10 = 1.8
    with _only_co2(readings):
        assert CabinCo2Rule().evaluate(RuleContext()) is None


def test_no_co2_readings_does_not_fire(client):
    with _only_co2([]):
        assert CabinCo2Rule().evaluate(RuleContext()) is None
