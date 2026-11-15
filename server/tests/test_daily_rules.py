"""R-SLP-01 / R-FAT-01 and the check-in privacy rules (owner: Shahd)."""
from __future__ import annotations

import json

import pytest

from server.rules.engine import run_rules
from server.tests._daily_helpers import daily_client, open_alert

FAT = "R-FAT-01"


@pytest.fixture
def c():
    with daily_client() as client:
        yield client


def test_fat_01_fires_on_seeded_data(c):
    a = open_alert(c, FAT)
    assert a["level"] == "review"
    assert a["title"] == "Possible fatigue pattern: short sleep and slower reaction time"
    assert a["sources"] == ["nasa-hrp-sleep-risk", "nasa-hrp-bmed-risk", "nasa-pvt-iss"]
    assert {"sleep-141", "sleep-142", "pvt-141", "pvt-142"} <= set(a["dataUsed"])
    assert "Today's check-in" in a["missing"]
    assert "ms" in a["whatChanged"] and "%" in a["whatChanged"] and " h " in a["whatChanged"]
    assert all("not confirmed" in f or "not a confirmed cause" in f for f in a["possibleFactors"])
    assert "dose" not in json.dumps(a).lower() and "medic" not in json.dumps(a).lower()


def test_slp_01_fires_on_seeded_data(c):
    a = open_alert(c, "R-SLP-01")
    assert a["level"] == "info"
    assert {"sleep-140", "sleep-141", "sleep-142"} <= set(a["dataUsed"])
    assert all(x.startswith("sleep-") or x.startswith("Cabin ") for x in a["dataUsed"])


def test_next_step_actions_carry_the_alert_id(c):
    a = open_alert(c, FAT)
    alerts = c.get("/api/daily/summary").json()["activeDailyAlerts"]
    fat = next(x for x in alerts if x["id"] == a["id"])
    routes = [s["action"]["route"] for s in fat["nextSteps"] if s.get("action")]
    assert routes == ["/daily#checkin", f"/attention?retest={a['id']}", "/daily#exercise"]


def test_no_duplicate_on_second_engine_run(c):
    from server.features.daily.engine_hooks import run_daily_engine

    first = open_alert(c, FAT)
    run_rules()
    run_daily_engine()
    c.post("/api/tests", json={"trialsMs": [340, 345, 350, 338, 342]})  # another slow routine test
    again = open_alert(c, FAT)  # asserts exactly one open
    assert again["id"] == first["id"]


def test_retest_sets_recheck(c):
    a = open_alert(c, FAT)
    r = c.post("/api/tests", json={"trialsMs": [280, 290, 285, 300, 275], "context": "retest", "relatedAlertId": a["id"]})
    assert r.status_code == 201 and r.json()["test"]["relatedAlertId"] == a["id"]
    after = c.get(f"/api/alerts/{a['id']}").json()
    assert after["status"] == "recheck"
    assert "Retest at " in after["whatChanged"]
    assert "median 285 ms (within your usual range)" in after["whatChanged"]
    # a retest never counts as a routine test, and never closes the alert
    assert open_alert(c, FAT)["id"] == a["id"]
    assert c.get("/api/tests/baseline").json()["n"] == 7


def test_retest_for_unknown_alert_is_404(c):
    r = c.post("/api/tests", json={"trialsMs": [300], "context": "retest", "relatedAlertId": "al-nope"})
    assert r.status_code == 404


def test_checkin_removes_missing(c):
    a = open_alert(c, FAT)
    assert "Today's check-in" in a["missing"]
    assert c.post("/api/checkins", json={"mood": 3, "stress": 4}).status_code == 201
    assert "Today's check-in" not in c.get(f"/api/alerts/{a['id']}").json()["missing"]


def test_skipped_checkin_also_counts(c):
    a = open_alert(c, FAT)
    r = c.post("/api/checkins", json={"skipped": True})
    assert r.status_code == 201 and r.json()["skipped"] is True
    assert "Today's check-in" not in c.get(f"/api/alerts/{a['id']}").json()["missing"]
    assert c.get("/api/daily/summary").json()["checkins"]["todayStatus"] == "skipped"


def test_checkin_needs_mood_and_stress_unless_skipped(c):
    assert c.post("/api/checkins", json={"mood": 3}).status_code == 422


def test_private_note_absent_from_summary_and_default_get(c):
    secret = "slept badly, worried about the EVA"
    assert c.post("/api/checkins", json={"mood": 2, "stress": 4, "notePrivate": secret}).json()["notePrivate"] == secret

    default = c.get("/api/checkins").json()
    assert default and all("notePrivate" not in x for x in default)
    summary = json.dumps(c.get("/api/daily/summary").json())
    assert secret not in summary and "notePrivate" not in summary

    with_private = c.get("/api/checkins?includePrivate=true").json()
    assert with_private[0]["notePrivate"] == secret


def test_sources_endpoint_lists_the_seven_ids(c):
    ids = [s["id"] for s in c.get("/api/daily/sources").json()]
    assert ids == [
        "nasa-hrp-sleep-risk", "nasa-hrp-bmed-risk", "nasa-pvt-iss", "nasa-hrp-hazards",
        "nasa-hrp-risks", "nasa-bone-risk", "nasa-hrp-ongoing",
    ]


def test_unmodified_seed_has_no_checkin_today(c):
    assert "Today's check-in" in open_alert(c, FAT)["missing"]


def test_retest_returns_before_vs_after(c):
    a = open_alert(c, FAT)
    r = c.post("/api/tests", json={"trialsMs": [280, 290, 285, 300, 275], "context": "retest",
                                   "relatedAlertId": a["id"]}).json()
    cmp = r["retest"]
    assert cmp["alertId"] == a["id"] and cmp["ruleId"] == FAT
    assert cmp["alertStatus"] == "recheck"
    assert set(cmp["beforeTestIds"]) == {"pvt-141", "pvt-142"}
    assert cmp["beforeMedianMs"] == pytest.approx(342, abs=15)
    assert cmp["afterMedianMs"] == 285
    assert cmp["diffMs"] == pytest.approx(285 - cmp["beforeMedianMs"])
    assert cmp["diffPct"] < 0  # faster after rest


def test_routine_test_has_no_retest_comparison(c):
    assert c.post("/api/tests", json={"trialsMs": [300, 310, 290]}).json()["retest"] is None


def test_fat_01_ignores_extended_tests(c):
    """R-FAT-01 compares quick routine tests only: a fast extended test changes nothing."""
    before = open_alert(c, FAT)
    c.post("/api/tests", json={"trialsMs": [250, 255, 260, 248, 252], "mode": "extended"})
    after = open_alert(c, FAT)
    assert after["id"] == before["id"]
    assert "median 342 ms over 2 routine tests" in after["whatChanged"]


def test_daily_thresholds_endpoint_has_sources(c):
    th = c.get("/api/daily/thresholds").json()
    for key in ("sleep_short_hours", "sleep_short_nights", "attention_slower_pct", "attention_baseline_n",
                "pvt_lapse_ms", "sleep_onset_shift_hours", "exercise_missed_days"):
        assert key in th, key
        assert th[key]["source"], key
        assert th[key]["note"], key
    assert th["sleep_onset_shift_hours"]["value"] == 2
    assert "experimental value" in th["sleep_onset_shift_hours"]["note"]


def test_summary_filter_includes_circ():
    from server.features.daily.summary import DAILY_RULE_PREFIXES

    assert set(DAILY_RULE_PREFIXES) == {"R-SLP", "R-FAT", "R-CIRC", "R-EX"}


# ---- service functions used by other features (assistant) ---------------------------------
def test_router_service_functions_never_include_private_notes(c):
    from server.features.daily import router as daily

    c.post("/api/checkins", json={"mood": 3, "stress": 2, "notePrivate": "secret-note-xyz"})
    rows = daily.list_checkins(n=14)
    assert rows and all("notePrivate" not in r for r in rows)
    assert "secret-note-xyz" not in json.dumps(rows)
    # the other names the assistant imports from this module return real data
    assert len(daily.list_sleep(nights=7)) == 7
    assert daily.list_tests(n=14) and isinstance(daily.exercise_plan(), list) and daily.exercise_plan()
    assert "fatigueFlag" in daily.today_plan()
