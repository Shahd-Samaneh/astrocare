"""Attention test (owner: Shahd): scoring, baseline window, API shape."""
from __future__ import annotations

from datetime import timedelta

import pytest

from server.core.config import iso, utcnow
from server.features.daily.attention_stats import DailyCognitiveTest, baseline_from, score_trials
from server.tests._daily_helpers import daily_client


@pytest.fixture
def c():
    with daily_client() as client:
        yield client


# ---- scoring ---------------------------------------------------------------------
def test_median_and_lapses():
    valid, median, lapses = score_trials([280, 300, 290, 610, 270])
    assert valid == [280, 300, 290, 610, 270]
    assert median == 290
    assert lapses == 1


def test_lapse_threshold_is_inclusive():
    # pvt_lapse_ms = 500: a response of exactly 500 ms counts as a lapse.
    assert score_trials([499, 500, 300])[2] == 1


def test_even_number_of_trials_uses_mean_of_middle_two():
    assert score_trials([300, 310, 320, 330])[1] == 315


def test_no_valid_trials_is_rejected():
    with pytest.raises(ValueError):
        score_trials([0, -5])


def test_server_computes_and_stores_false_starts(c):
    r = c.post("/api/tests", json={"trialsMs": [280, 300, 290, 610, 270], "falseStarts": 2})
    assert r.status_code == 201
    body = r.json()
    t = body["test"]
    assert (t["medianMs"], t["lapses"], t["falseStarts"], t["context"]) == (290, 1, 2, "routine")
    assert {"pctVsBaseline", "withinRange", "baseline"} <= body.keys()
    stored = c.get("/api/tests?n=1").json()[0]
    assert stored["id"] == t["id"] and stored["falseStarts"] == 2


def test_all_lapses_still_save(c):
    r = c.post("/api/tests", json={"trialsMs": [600, 700, 800, 900, 5000], "falseStarts": 0})
    assert r.status_code == 201
    t = r.json()["test"]
    assert t["lapses"] == 5 and t["medianMs"] == 800
    assert r.json()["withinRange"] is False


def test_invalid_trials_return_422(c):
    assert c.post("/api/tests", json={"trialsMs": [0, -1]}).status_code == 422
    assert c.post("/api/tests", json={"trialsMs": []}).status_code == 422


# ---- baseline window -------------------------------------------------------------------
def _t(i: int, hours_ago: float, median: float, context: str = "routine") -> DailyCognitiveTest:
    return DailyCognitiveTest(
        id=f"t{i}", ts=iso(utcnow() - timedelta(hours=hours_ago)), trials_ms=[median], median_ms=median,
        lapses=0, false_starts=0, context=context,
    )


def test_baseline_uses_routine_tests_before_last_48h():
    now = utcnow()
    tests = [
        _t(0, 2, 999),                       # last 48 h: excluded
        _t(1, 47, 999),                      # last 48 h: excluded
        _t(2, 50, 999, context="retest"),    # retest: excluded
        *[_t(10 + k, 49 + 24 * k, 300 + k) for k in range(9)],  # 9 older routine tests
    ]
    b = baseline_from(tests, now)
    assert b.n == 7  # attention_baseline_n
    assert b.test_ids == [f"t{10 + k}" for k in range(7)]  # the 7 newest of the older ones
    assert b.median_ms == 303
    assert (b.range_low_ms, b.range_high_ms) == (300, 306)  # min / max


def test_baseline_with_fewer_than_three_tests_uses_plus_minus_10_pct():
    b = baseline_from([_t(1, 60, 300), _t(2, 90, 320)], utcnow())
    assert b.n == 2 and b.median_ms == 310
    assert b.range_low_ms == pytest.approx(279) and b.range_high_ms == pytest.approx(341)


def test_baseline_empty_without_history():
    b = baseline_from([_t(1, 1, 300)], utcnow())
    assert b.n == 0 and b.median_ms is None


def test_baseline_endpoint_on_seeded_data(c):
    b = c.get("/api/tests/baseline").json()
    assert b["n"] == 7
    assert b["medianMs"] == pytest.approx(285, abs=10)
    assert b["rangeLowMs"] <= b["medianMs"] <= b["rangeHighMs"]


def test_tests_are_newest_first_with_context(c):
    tests = c.get("/api/tests?n=10").json()
    assert len(tests) == 10
    assert [t["ts"] for t in tests] == sorted((t["ts"] for t in tests), reverse=True)
    assert all(t["context"] == "routine" for t in tests)
