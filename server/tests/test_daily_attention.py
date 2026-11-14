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


# ---- hours awake (result context) -------------------------------------------------
def test_sleep_context_hours_awake(c):
    from server.core import db
    from server.core.config import parse_ts

    last = db.query("sleep_sessions", order_by='"end" DESC', limit=1)[0]
    ts = iso(parse_ts(last["end"]) + timedelta(hours=9, minutes=6))
    ctx = c.post("/api/tests", json={"trialsMs": [300, 310, 290], "ts": ts}).json()["sleepContext"]
    assert ctx["sleepId"] == last["id"]
    assert ctx["hoursAwake"] == 9.1
    assert ctx["sleptHours"] == round(last["duration_min"] / 60, 1)
    assert ctx["source"] == "simulated"


def test_sleep_context_unknown_without_sleep(c):
    from server.core import db

    with db.connect() as conn:
        conn.execute("DELETE FROM sleep_sessions")
    ctx = c.post("/api/tests", json={"trialsMs": [300, 310, 290]}).json()["sleepContext"]
    assert ctx["hoursAwake"] is None and ctx["sleptHours"] is None


# ---- sleepiness (KSS) ---------------------------------------------------------------
@pytest.mark.parametrize("kss", [1, 5, 9, None])
def test_kss_valid_values_are_stored(c, kss):
    body = {"trialsMs": [300, 310, 290]}
    if kss is not None:
        body["sleepinessKss"] = kss
    t = c.post("/api/tests", json=body).json()["test"]
    assert t["sleepinessKss"] == kss
    assert c.get("/api/tests?n=1").json()[0]["sleepinessKss"] == kss


@pytest.mark.parametrize("kss", [0, 10, -1])
def test_kss_out_of_range_is_rejected(c, kss):
    assert c.post("/api/tests", json={"trialsMs": [300], "sleepinessKss": kss}).status_code == 422


# ---- extended mode: PVT outcome measures -------------------------------------------------
def test_pvt_measures_on_five_trials():
    from server.features.daily.attention_stats import pvt_measures

    m = pvt_measures([200, 250, 300, 400, 1000], false_starts=1)
    assert m.n == 5
    assert m.mean_ms == 430.0
    assert m.fastest10_mean_ms == 200.0  # 10 % of 5 rounds to 0 → at least 1 response
    assert m.slowest10_mean_ms == 1000.0
    # mean of 1/RT in 1/s: (5 + 4 + 3.333 + 2.5 + 1) / 5
    assert m.response_speed == pytest.approx((5 + 4 + 1000 / 300 + 2.5 + 1) / 5, abs=1e-3)
    assert m.lapses == 1 and m.false_starts == 1


def test_pvt_measures_ten_percent_of_twenty():
    from server.features.daily.attention_stats import pvt_measures

    rts = [300.0] * 16 + [200.0, 210.0] + [600.0, 700.0]
    m = pvt_measures(rts)
    assert m.fastest10_mean_ms == 205.0  # 2 fastest
    assert m.slowest10_mean_ms == 650.0  # 2 slowest
    assert m.lapses == 2


def test_extended_post_returns_measures_and_stores_mode(c):
    trials = [300 + i for i in range(20)]
    offsets = [5000.0 * (i + 1) for i in range(20)]
    r = c.post("/api/tests", json={"trialsMs": trials, "mode": "extended", "trialOffsetsMs": offsets})
    assert r.status_code == 201
    t = r.json()["test"]
    assert t["mode"] == "extended"
    assert t["measures"]["n"] == 20 and t["measures"]["fastest10MeanMs"] == 300.5
    stored = c.get("/api/tests?n=1").json()[0]
    assert stored["mode"] == "extended" and stored["trialOffsetsMs"] == offsets


def test_offsets_must_match_trials(c):
    r = c.post("/api/tests", json={"trialsMs": [300, 310], "trialOffsetsMs": [1000.0]})
    assert r.status_code == 422


# ---- same-mode baseline and "building" ---------------------------------------------------
def test_baseline_is_per_mode(c):
    for days_ago in (3, 4):
        ts = iso(utcnow() - timedelta(days=days_ago))
        c.post("/api/tests", json={"trialsMs": [400, 410, 420], "mode": "extended", "ts": ts})
    quick = c.get("/api/tests/baseline").json()
    ext = c.get("/api/tests/baseline?mode=extended").json()
    assert quick["mode"] == "quick" and quick["n"] == 7 and quick["building"] is False
    assert quick["medianMs"] == pytest.approx(285, abs=10)  # extended tests never enter it
    assert ext["mode"] == "extended" and ext["n"] == 2 and ext["medianMs"] == 410
    assert ext["building"] is True and ext["needed"] == 3


def test_first_extended_test_is_building_baseline(c):
    r = c.post("/api/tests", json={"trialsMs": [300, 320, 340], "mode": "extended"}).json()
    assert r["baseline"]["n"] == 0 and r["baseline"]["building"] is True
    assert r["withinRange"] is None and r["pctVsBaseline"] is None


def test_building_baseline_gives_no_verdict(c):
    ts = iso(utcnow() - timedelta(days=3))
    c.post("/api/tests", json={"trialsMs": [400, 410, 420], "mode": "extended", "ts": ts})
    r = c.post("/api/tests", json={"trialsMs": [800, 810, 820], "mode": "extended"}).json()
    assert r["baseline"]["n"] == 1 and r["baseline"]["building"] is True
    assert r["pctVsBaseline"] is not None  # shown as preliminary
    assert r["withinRange"] is None



# ---- input method ------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["mouse", "touch", "keyboard"])
def test_input_method_is_stored(c, method):
    t = c.post("/api/tests", json={"trialsMs": [300, 310, 290], "inputMethod": method}).json()["test"]
    assert t["inputMethod"] == method
    assert c.get("/api/tests?n=1").json()[0]["inputMethod"] == method


def test_unknown_input_method_is_rejected(c):
    assert c.post("/api/tests", json={"trialsMs": [300], "inputMethod": "pen"}).status_code == 422


def test_input_differs_from_usual_baseline_input(c):
    for days_ago in (3, 4, 5):
        ts = iso(utcnow() - timedelta(days=days_ago))
        c.post("/api/tests", json={"trialsMs": [400, 410, 420], "mode": "extended", "inputMethod": "mouse", "ts": ts})
    same = c.post("/api/tests", json={"trialsMs": [400], "mode": "extended", "inputMethod": "mouse"}).json()
    other = c.post("/api/tests", json={"trialsMs": [400], "mode": "extended", "inputMethod": "touch"}).json()
    assert same["baseline"]["usualInputMethod"] == "mouse"
    assert same["inputDiffers"] is False
    assert other["inputDiffers"] is True


def test_no_input_note_when_baseline_input_unknown(c):
    # seeded (simulated) tests have no input method recorded
    r = c.post("/api/tests", json={"trialsMs": [300, 310, 290], "inputMethod": "touch"}).json()
    assert r["baseline"]["usualInputMethod"] is None and r["inputDiffers"] is False
