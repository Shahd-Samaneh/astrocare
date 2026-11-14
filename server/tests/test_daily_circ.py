"""R-CIRC-01 irregular sleep schedule (owner: Shahd), on synthetic nights."""
from __future__ import annotations

from datetime import timedelta

import pytest

from server.core import db
from server.core.config import iso
from server.core.status import mission_clock, mission_day_start
from server.rules.base import RuleContext
from server.rules.r_circ_01_irregular_schedule import IrregularScheduleRule
from server.tests._daily_helpers import daily_client

CIRC = "R-CIRC-01"


@pytest.fixture
def c():
    with daily_client() as client:
        yield client


def _set_nights(bedtimes: dict[int, float]) -> None:
    """Replace all sleep with one 7 h night per entry: {nights_ago: bedtime hour (mission time, may be ≥ 24)}.

    nights_ago 0 = last night (woke up today). Bedtime 23 = 23:00 the evening before,
    24.5 = 00:30 on the wake-up day.
    """
    today_start = mission_day_start()
    with db.connect() as conn:
        conn.execute("DELETE FROM sleep_sessions")
    for ago, hour in bedtimes.items():
        start = today_start - timedelta(days=ago) - timedelta(hours=24) + timedelta(hours=hour)
        db.insert("sleep_sessions", {
            "id": f"syn-{ago}", "start": iso(start), "end": iso(start + timedelta(hours=7)),
            "duration_min": 420, "awakenings": 1, "self_quality": 3, "source": "manual",
        })


def _open_circ() -> list[dict]:
    return db.query("alerts", "rule_id = ? AND status != 'closed'", (CIRC,))


def test_fires_when_bedtimes_shift_more_than_threshold(c):
    _set_nights({2: 22.0, 1: 25.0, 0: 26.0})  # 22:00, 01:00, 02:00 → 4 h spread
    d = IrregularScheduleRule().evaluate(RuleContext())
    assert d is not None and d.level == "info"
    assert "22:00" in d.what_changed and "01:00" in d.what_changed and "02:00" in d.what_changed
    assert "4.0 h" in d.what_changed
    assert d.missing == []
    assert all("not confirmed" in f for f in d.possible_factors)
    assert d.next_steps[0].text == "Review tonight's sleep window"
    assert d.next_steps[0].action.route == "/daily#sleep"


def test_quiet_when_schedule_is_regular_across_midnight(c):
    _set_nights({2: 23.5, 1: 24.25, 0: 23.75})  # 23:30, 00:15, 23:45 → 0.75 h
    assert IrregularScheduleRule().evaluate(RuleContext()) is None


def test_missing_nights_are_listed(c):
    _set_nights({1: 22.0, 0: 26.0})  # no data for the night 2 days ago
    d = IrregularScheduleRule().evaluate(RuleContext())
    today = mission_clock()[1]
    assert d is not None
    assert d.missing == [f"No sleep data for night {today - 2}"]


def test_needs_two_nights_to_compare(c):
    _set_nights({0: 26.0})
    assert IrregularScheduleRule().evaluate(RuleContext()) is None


def test_one_open_alert_and_summary_lists_it(c):
    from server.features.daily.engine_hooks import run_daily_engine

    _set_nights({2: 22.0, 1: 25.0, 0: 26.0})
    run_daily_engine()
    run_daily_engine()
    c.post("/api/checkins", json={"skipped": True})  # another engine run via a POST
    assert len(_open_circ()) == 1
    alert = _open_circ()[0]
    assert alert["sources"] == ["nasa-hrp-sleep-risk"]
    summary = c.get("/api/daily/summary").json()["activeDailyAlerts"]
    circ = next(a for a in summary if a["ruleId"] == CIRC)
    assert circ["nextSteps"][0]["action"]["route"] == "/daily#sleep"
