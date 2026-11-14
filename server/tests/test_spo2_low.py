"""Tests for R-SPO2-01 (low SpO₂ episode)."""
from __future__ import annotations

from contextlib import contextmanager

from server.core import db
from server.rules.base import RuleContext
from server.rules.r_spo2_01_low import LowSpo2Rule

# spo2_min is 92; low values sit below it. Timestamps are far-future so the
# inserted readings are the most recent ones the rule inspects.


def _insert(readings: list[tuple[float, str, int]]) -> list[str]:
    """Each tuple is (value, quality, minute_offset). Returns inserted ids."""
    ids = []
    for value, quality, minute in readings:
        rid = db.new_id("r-spo2test")
        db.insert("readings", {
            "id": rid, "astronaut_id": "c2", "metric": "spo2", "value": value,
            "unit": "%", "ts": f"2030-01-01T00:{minute:02d}:00Z", "source": "manual", "quality": quality,
        })
        ids.append(rid)
    return ids


@contextmanager
def _readings(readings: list[tuple[float, str, int]]):
    ids = _insert(readings)
    try:
        yield
    finally:
        from server.core.db import connect

        with connect() as conn:
            conn.executemany("DELETE FROM readings WHERE id = ?", [(i,) for i in ids])


def test_good_quality_episode_is_urgent(client):
    with _readings([(90, "good", 0), (89, "good", 6)]):
        draft = LowSpo2Rule().evaluate(RuleContext())
        assert draft is not None
        assert draft.level == "urgent"
        assert draft.dedupe_key == "spo2-low-urgent"
        assert any(s.locked_for_cmo for s in draft.next_steps)  # CMO notified
        assert "cause" not in draft.what_changed.lower()


def test_low_quality_episode_is_info(client):
    with _readings([(90, "good", 0), (89, "low", 6)]):
        draft = LowSpo2Rule().evaluate(RuleContext())
        assert draft is not None
        assert draft.level == "info"
        assert "recheck sensor" in draft.title.lower()
        assert draft.dedupe_key == "spo2-low-info"
        assert not any(s.locked_for_cmo for s in draft.next_steps)  # not a clinical event


def test_single_low_reading_does_not_fire(client):
    with _readings([(90, "good", 0)]):
        assert LowSpo2Rule().evaluate(RuleContext()) is None


def test_recovered_latest_does_not_fire(client):
    # Two lows, but the most recent reading is back above the threshold.
    with _readings([(90, "good", 0), (89, "good", 6), (97, "good", 12)]):
        assert LowSpo2Rule().evaluate(RuleContext()) is None


def test_episode_shorter_than_window_does_not_fire(client):
    # Two low readings only 2 min apart (< spo2_low_minutes = 5).
    with _readings([(90, "good", 0), (89, "good", 2)]):
        assert LowSpo2Rule().evaluate(RuleContext()) is None


def test_no_spo2_data_does_not_fire(client):
    from server.core.db import connect

    saved = db.query("readings", "metric = 'spo2'")
    with connect() as conn:
        conn.execute("DELETE FROM readings WHERE metric = 'spo2'")
    try:
        assert LowSpo2Rule().evaluate(RuleContext()) is None
    finally:
        if saved:
            db.insert_many("readings", saved)
