"""Tests for R-HR-01 (heart rate elevated above personal baseline).

Readings are inserted with far-future timestamps so they are the most recent
good-quality heart-rate readings the rule inspects, then removed afterwards.
"""
from __future__ import annotations

from contextlib import contextmanager

from server.core import db
from server.rules.base import RuleContext
from server.rules.r_hr_01_elevated import ElevatedHeartRateRule


def _baseline_hr(ctx: RuleContext):
    base = ctx.profile.baseline["heart_rate"]
    return base.mean, base.sd


def _insert(values_quality: list[tuple[float, str]]) -> list[str]:
    """Insert HR readings at 2030-01-01T00:00, 00:30, ... (most recent). Returns ids."""
    ids = []
    for i, (value, quality) in enumerate(values_quality):
        rid = db.new_id("r-hrtest")
        db.insert("readings", {
            "id": rid, "astronaut_id": "c2", "metric": "heart_rate", "value": value,
            "unit": "bpm", "ts": f"2030-01-01T{i // 2:02d}:{30 * (i % 2):02d}:00Z",
            "source": "manual", "quality": quality,
        })
        ids.append(rid)
    return ids


@contextmanager
def _readings(values_quality: list[tuple[float, str]]):
    ids = _insert(values_quality)
    try:
        yield
    finally:
        from server.core.db import connect

        with connect() as conn:
            conn.executemany("DELETE FROM readings WHERE id = ?", [(i,) for i in ids])


def test_fires_on_three_high_in_a_row(client):
    ctx = RuleContext()
    mean, sd = _baseline_hr(ctx)
    high = mean + 2 * sd + 5
    with _readings([(high, "good"), (high, "good"), (high, "good")]):
        draft = ElevatedHeartRateRule().evaluate(RuleContext())
        assert draft is not None
        assert draft.level == "review"
        assert "possible" not in draft.what_changed.lower()  # cause-neutral wording
        assert len(draft.data_used) >= 3
        assert any(s.locked_for_cmo for s in draft.next_steps)  # clinical step is CMO-locked
        assert any(not s.locked_for_cmo for s in draft.next_steps)  # recheck-at-rest step


def test_does_not_fire_on_only_two_high(client):
    ctx = RuleContext()
    mean, sd = _baseline_hr(ctx)
    high = mean + 2 * sd + 5
    # Most recent reading is within baseline, so the last 3 are not all high.
    with _readings([(high, "good"), (high, "good"), (mean, "good")]):
        assert ElevatedHeartRateRule().evaluate(RuleContext()) is None


def test_low_quality_high_readings_do_not_count(client):
    ctx = RuleContext()
    mean, sd = _baseline_hr(ctx)
    high = mean + 2 * sd + 5
    # Three high readings but all low-quality: skipped, so the rule cannot fire on them.
    with _readings([(high, "low"), (high, "low"), (high, "low")]):
        assert ElevatedHeartRateRule().evaluate(RuleContext()) is None


def test_does_not_fire_without_baseline(client):
    ctx = RuleContext()
    mean, sd = _baseline_hr(ctx)
    high = mean + 2 * sd + 5
    profile = db.query("profiles", limit=1)[0]
    original = dict(profile["baseline"])
    without_hr = {k: v for k, v in original.items() if k != "heart_rate"}
    db.update("profiles", profile["id"], {"baseline": without_hr})
    try:
        with _readings([(high, "good"), (high, "good"), (high, "good")]):
            assert ElevatedHeartRateRule().evaluate(RuleContext()) is None
    finally:
        db.update("profiles", profile["id"], {"baseline": original})
