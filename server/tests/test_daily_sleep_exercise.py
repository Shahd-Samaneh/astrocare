"""Nadia's part of Daily health: sleep, exercise, today plan, rule R-EX-01.

These tests mount Nadia's three routers on their own small app and use their own
throw-away database (seeded like the demo), so they don't depend on how
server/features/daily/router.py includes them, and they leave other tests' data alone.
Every test starts from the seeded state (see the `snapshot` fixture).
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.core import db
from server.core.config import iso, utcnow
from server.core.status import mission_day_start

TABLES_TO_RESTORE = ("sleep_sessions", "cognitive_tests", "checkins", "exercise_logs", "alerts", "resources")


@pytest.fixture(scope="module", autouse=True)
def daily_db(tmp_path_factory):
    """A seeded database of its own for this module."""
    old = os.environ["ASTROCARE_DB_PATH"]
    os.environ["ASTROCARE_DB_PATH"] = str(tmp_path_factory.mktemp("daily") / "daily.db")
    from server.core.seed import seed
    from server.rules.engine import run_rules

    seed()
    run_rules()
    yield
    os.environ["ASTROCARE_DB_PATH"] = old


@pytest.fixture(scope="module")
def client(daily_db):
    from server.features.daily import exercise, sleep, today

    app = FastAPI()
    for module in (sleep, exercise, today):
        app.include_router(module.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def snapshot(daily_db):
    """Put the tables these tests change back to the seeded state after each test."""
    saved = {t: db.query(t) for t in TABLES_TO_RESTORE}
    yield
    with db.connect() as conn:
        for t in TABLES_TO_RESTORE:
            conn.execute(f'DELETE FROM "{t}"')
    for t, rows in saved.items():
        db.insert_many(t, rows)


def _delete(table: str, where: str = "1=1", params: tuple = ()) -> None:
    with db.connect() as conn:
        conn.execute(f'DELETE FROM "{table}" WHERE {where}', params)


def _fatigue_alert(status: str = "new") -> None:
    db.insert("alerts", {
        "id": "al-test-fat", "rule_id": "R-FAT-01", "level": "review", "ts": iso(utcnow()),
        "title": "Possible fatigue pattern", "what_changed": "", "data_used": [], "missing": [],
        "possible_factors": [], "next_steps": [], "status": status, "sources": [], "dedupe_key": "test",
    })


# ---- sleep: validation -------------------------------------------------------------------
def _sleep_body(**over):
    end = utcnow()
    body = {"start": iso(end - timedelta(hours=7)), "end": iso(end), "awakenings": 1, "selfQuality": 4}
    return {**body, **over}


def test_manual_sleep_is_saved_and_validated(client):
    ok = client.post("/api/sleep", json=_sleep_body())
    assert ok.status_code == 201
    saved = ok.json()
    assert saved["source"] == "manual" and saved["durationMin"] == 420 and saved["selfQuality"] == 4


def test_manual_sleep_rejects_bad_input(client):
    now = utcnow()
    cases = {
        "end before start": _sleep_body(start=iso(now), end=iso(now - timedelta(hours=1))),
        "end equals start": _sleep_body(start=iso(now), end=iso(now)),
        "over 16 hours": _sleep_body(start=iso(now - timedelta(hours=17)), end=iso(now)),
        "negative awakenings": _sleep_body(awakenings=-1),
        "rating too high": _sleep_body(selfQuality=6),
        "rating too low": _sleep_body(selfQuality=0),
        "not a date": _sleep_body(start="yesterday"),
    }
    before = db.count("sleep_sessions")
    for name, body in cases.items():
        r = client.post("/api/sleep", json=body)
        assert r.status_code == 422, name
        assert isinstance(r.json()["detail"], str) and r.json()["detail"], name  # a readable message
    assert db.count("sleep_sessions") == before


def test_exactly_16_hours_and_no_rating_are_allowed(client):
    now = utcnow()
    r = client.post("/api/sleep", json={"start": iso(now - timedelta(hours=16)), "end": iso(now), "awakenings": 0})
    assert r.status_code == 201 and r.json()["selfQuality"] is None


def test_rating_patch(client):
    last = client.get("/api/sleep/summary").json()["lastNight"]
    ok = client.patch(f"/api/sleep/{last['id']}/rating", json={"selfQuality": 5})
    assert ok.status_code == 200 and ok.json()["selfQuality"] == 5
    assert client.patch(f"/api/sleep/{last['id']}/rating", json={"selfQuality": 6}).status_code == 422
    assert client.patch("/api/sleep/nope/rating", json={"selfQuality": 3}).status_code == 404


# ---- sleep: summary and personal average ------------------------------------------------------
def test_summary_has_mission_days_and_flags_short_nights(client):
    s = client.get("/api/sleep/summary?days=7").json()
    assert len(s["nights"]) == 7
    assert [n["missionDay"] for n in s["nights"]] == list(range(136, 143))
    assert [n["missionDay"] for n in s["nights"] if n["short"]] == [141, 142]
    assert s["lastNight"]["id"] == s["nights"][-1]["id"]
    assert set(s["nights"][0]) >= {"date", "missionDay", "hours", "awakenings", "selfQuality"}


def test_personal_average_is_mean_of_first_three_mission_days(client):
    rows = db.query("sleep_sessions", order_by="start")
    expected = sum(r["duration_min"] / 60 for r in rows[:3]) / 3
    assert client.get("/api/sleep/summary?days=7").json()["personalAvgHours"] == pytest.approx(expected, abs=0.01)


def test_personal_average_with_fewer_than_three_nights():
    from server.features.daily.sleep import personal_avg_hours

    end = utcnow()
    rows = [
        {"id": "a", "start": iso(end - timedelta(hours=8)), "end": iso(end), "duration_min": 480},
        {"id": "b", "start": iso(end - timedelta(days=1, hours=6)), "end": iso(end - timedelta(days=1)), "duration_min": 360},
    ]
    assert personal_avg_hours(rows) == 7.0
    assert personal_avg_hours([]) is None


def test_sleep_summary_service_function():
    from server.features.daily.sleep import sleep_summary

    s = sleep_summary(3)
    assert len(s["nights"]) == 3 and s["shortThresholdHours"] == 6


# ---- exercise: plan and alternatives -------------------------------------------------------------
def test_plan_resolves_equipment_and_status(client):
    day = client.get("/api/exercise/plan?day=142").json()
    assert len(day) == 1
    item = day[0]
    assert item["id"] == "ex-142" and item["intensity"] == "hard" and item["equipment"]["id"] == "eq-ared"
    assert item["equipmentStatus"] == "available" and item["log"] is None
    week = client.get("/api/exercise/plan").json()
    assert [p["day"] for p in week] == list(range(140, 147))
    assert all(p["day"] is not None for p in week)  # alternatives-only items are not scheduled


def test_fatigue_ranks_lighter_and_shorter_first(client):
    r = client.get("/api/exercise/alternatives?planId=ex-142&reason=fatigue").json()
    alts = r["alternatives"]
    assert alts and "message" not in r
    order = {"light": 0, "moderate": 1, "hard": 2}
    keys = [(order[a["intensity"]], a["durationMin"]) for a in alts]
    assert keys == sorted(keys)
    assert alts[0]["intensity"] == "light" and "Lighter" in alts[0]["why"]
    assert any(any(w.startswith("Uses ") and w.endswith(", available") for w in a["why"]) for a in alts)


def test_every_hard_session_has_a_lighter_alternative(client):
    order = {"light": 0, "moderate": 1, "hard": 2}
    for item in client.get("/api/exercise/plan").json():
        if item["intensity"] == "hard":
            alts = client.get(f"/api/exercise/alternatives?planId={item['id']}&reason=fatigue").json()["alternatives"]
            assert any(order[a["intensity"]] < 2 for a in alts), item["id"]


def test_alternatives_exclude_equipment_in_maintenance(client):
    before = client.get("/api/exercise/alternatives?planId=ex-142&reason=fatigue").json()["alternatives"]
    assert "alt-cevis-easy" in [a["id"] for a in before]
    db.update("resources", "eq-cycle", {"status": "maintenance"})
    after = client.get("/api/exercise/alternatives?planId=ex-142&reason=fatigue").json()["alternatives"]
    assert "alt-cevis-easy" not in [a["id"] for a in after]
    assert [a["id"] for a in after] == [a["id"] for a in before if a["id"] != "alt-cevis-easy"]


def test_low_stock_equipment_is_still_offered(client):
    ids = [a["id"] for a in client.get("/api/exercise/alternatives?planId=ex-142&reason=fatigue").json()["alternatives"]]
    assert "alt-bands-circuit" in ids  # eq-bands is `low`, not unavailable


def test_reason_equipment_drops_the_same_equipment():
    from server.features.daily.exercise import rank_alternatives

    plan = {"id": "x", "day": 1, "intensity": "hard", "durationMin": 45, "equipmentId": "eq-cycle",
            "alternatives": ["alt-cevis-easy", "alt-mobility"]}
    assert [a["id"] for a in rank_alternatives(plan, "equipment")["alternatives"]] == ["alt-mobility"]
    assert [a["id"] for a in rank_alternatives(plan, "fatigue")["alternatives"]] == ["alt-mobility", "alt-cevis-easy"]


def test_empty_alternatives_return_a_message(client):
    r = client.get("/api/exercise/alternatives?planId=ex-146&reason=fatigue").json()
    assert r["alternatives"] == [] and "Try rescheduling" in r["message"]


def test_message_names_the_missing_equipment():
    from server.features.daily.exercise import rank_alternatives

    plan = {"id": "x", "day": 1, "intensity": "hard", "durationMin": 45, "equipmentId": "eq-cycle",
            "alternatives": ["alt-cevis-easy"]}
    out = rank_alternatives(plan, "equipment")
    assert out["alternatives"] == []
    assert out["message"] == "No alternative available without Cycle ergometer. Try rescheduling."


def test_unknown_plan_is_404(client):
    assert client.get("/api/exercise/alternatives?planId=nope&reason=fatigue").status_code == 404
    assert client.post("/api/exercise/log", json={"planId": "nope", "status": "done"}).status_code == 404


# ---- exercise: log -----------------------------------------------------------------------------------
def test_log_with_alternative_is_saved_as_partial(client):
    r = client.post("/api/exercise/log", json={
        "planId": "ex-142", "status": "partial", "reason": "fatigue", "alternativeId": "alt-mobility",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "partial" and body["alternativeId"] == "alt-mobility" and body["reason"] == "fatigue"
    stored = db.query("exercise_logs", "plan_id = ?", ("ex-142",))
    assert [(x["status"], x["alternative_id"]) for x in stored] == [("partial", "alt-mobility")]
    item = client.get("/api/exercise/plan?day=142").json()[0]
    assert item["log"]["status"] == "partial" and item["log"]["alternativeType"] == "Mobility and stretching"


def test_log_rejects_bad_status_reason_combinations(client):
    bad = [
        {"planId": "ex-142", "status": "done", "reason": "pain"},
        {"planId": "ex-142", "status": "skipped"},
        {"planId": "ex-142", "status": "skipped", "reason": "time", "alternativeId": "alt-mobility"},
        {"planId": "ex-142", "status": "partial", "reason": "fatigue"},
        {"planId": "ex-142", "status": "partial", "alternativeId": "alt-mobility"},
        {"planId": "ex-142", "status": "partial", "reason": "fatigue", "alternativeId": "alt-t2-easy"},  # not this plan's
    ]
    for body in bad:
        assert client.post("/api/exercise/log", json=body).status_code == 422, body
    assert db.count("exercise_logs", "plan_id = ?", ("ex-142",)) == 0


def test_log_rejects_an_unavailable_alternative(client):
    db.update("resources", "eq-cycle", {"status": "out_of_stock"})
    r = client.post("/api/exercise/log", json={
        "planId": "ex-142", "status": "partial", "reason": "fatigue", "alternativeId": "alt-cevis-easy",
    })
    assert r.status_code == 422 and "not available" in r.json()["detail"]


def test_exercise_summary():
    from server.features.daily.exercise import exercise_summary

    s = exercise_summary(7)
    assert s["plannedToday"]["id"] == "ex-142" and s["loggedToday"] is None
    assert (s["done"], s["partial"], s["skipped"], s["notLogged"]) == (1, 1, 0, 0)
    assert s["skipReasons"] == {"fatigue": 1}


# ---- today plan ------------------------------------------------------------------------------------------
def _items(client):
    r = client.get("/api/today/plan").json()
    return r, {i["kind"]: i for i in r["items"]}


def test_today_plan_shape_and_routes(client):
    plan, items = _items(client)
    assert plan["missionDay"] == 142
    assert {k: i["route"] for k, i in items.items()} == {
        "checkin": "/daily#checkin", "attention": "/attention", "exercise": "/daily#exercise", "sleep_rating": "/daily#sleep",
    }
    assert all(i["status"] in ("todo", "done", "skipped") for i in items.values())


def test_today_plan_checkin_status(client):
    assert _items(client)[1]["checkin"]["status"] == "todo"  # the seed has no check-in today
    db.insert("checkins", {"id": "ci-t1", "ts": iso(utcnow()), "mood": None, "stress": None, "note_private": None, "skipped": True})
    assert _items(client)[1]["checkin"]["status"] == "skipped"
    db.insert("checkins", {"id": "ci-t2", "ts": iso(utcnow()), "mood": 3, "stress": 2, "note_private": None, "skipped": False})
    assert _items(client)[1]["checkin"]["status"] == "done"


def test_today_plan_attention_status(client):
    _delete("cognitive_tests", "ts >= ?", (iso(mission_day_start()),))
    assert _items(client)[1]["attention"]["status"] == "todo"
    db.insert("cognitive_tests", {"id": "pvt-t1", "ts": iso(utcnow()), "trials_ms": [280, 290, 300, 310, 320],
                                  "median_ms": 300.0, "lapses": 0, "false_starts": 0})
    assert _items(client)[1]["attention"]["status"] == "done"


def test_today_plan_exercise_status(client):
    assert _items(client)[1]["exercise"]["status"] == "todo"
    client.post("/api/exercise/log", json={"planId": "ex-142", "status": "skipped", "reason": "time"})
    assert _items(client)[1]["exercise"]["status"] == "skipped"
    client.post("/api/exercise/log", json={"planId": "ex-142", "status": "done"})
    assert _items(client)[1]["exercise"]["status"] == "done"


def test_today_plan_sleep_rating_status(client):
    last = client.get("/api/sleep/summary").json()["lastNight"]
    db.update("sleep_sessions", last["id"], {"self_quality": None})
    assert _items(client)[1]["sleep_rating"]["status"] == "todo"
    client.patch(f"/api/sleep/{last['id']}/rating", json={"selfQuality": 3})
    assert _items(client)[1]["sleep_rating"]["status"] == "done"


def test_fatigue_flag_follows_the_r_fat_01_alert(client):
    _delete("alerts", "rule_id = ?", ("R-FAT-01",))
    assert client.get("/api/today/plan").json()["fatigueFlag"] is False
    _fatigue_alert("new")
    assert client.get("/api/today/plan").json()["fatigueFlag"] is True
    db.update("alerts", "al-test-fat", {"status": "recheck"})
    assert client.get("/api/today/plan").json()["fatigueFlag"] is True  # only `closed` clears it
    db.update("alerts", "al-test-fat", {"status": "closed"})
    assert client.get("/api/today/plan").json()["fatigueFlag"] is False


# ---- rule R-EX-01 ----------------------------------------------------------------------------------------------
def _open_ex_alerts():
    return db.query("alerts", "rule_id = ? AND status != 'closed'", ("R-EX-01",))


def test_r_ex_01_is_discovered_and_quiet_on_the_seeded_week():
    from server.rules.base import RuleContext
    from server.rules.engine import discover_rules
    from server.rules.r_ex_01_missed_exercise import MissedExerciseRule

    assert "R-EX-01" in [r.id for r in discover_rules()]
    assert MissedExerciseRule().evaluate(RuleContext()) is None  # day 140 done, day 141 partial


def test_r_ex_01_fires_on_two_missed_days_and_does_not_duplicate():
    from server.rules.engine import run_rules

    _delete("exercise_logs")  # days 140 and 141 are now "not logged"
    run_rules()
    alerts = _open_ex_alerts()
    assert len(alerts) == 1
    a = alerts[0]
    assert a["level"] == "info" and a["sources"] == ["nasa-hrp-risks", "nasa-bone-risk"]
    assert a["next_steps"][0]["text"] == "Pick an alternative"
    assert "140" in a["what_changed"] and "141" in a["what_changed"]
    assert a["missing"] and all("Exercise log" in m for m in a["missing"])

    run_rules()
    run_rules()
    assert len(_open_ex_alerts()) == 1


def test_r_ex_01_counts_skipped_logs_too():
    from server.rules.base import RuleContext
    from server.rules.r_ex_01_missed_exercise import MissedExerciseRule

    _delete("exercise_logs")
    for i, plan in enumerate(("ex-140", "ex-141")):
        db.insert("exercise_logs", {"id": f"exl-s{i}", "plan_id": plan, "ts": iso(utcnow()), "status": "skipped",
                                    "reason": "fatigue", "alternative_id": None})
    draft = MissedExerciseRule().evaluate(RuleContext())
    assert draft is not None and "fatigue" in draft.what_changed and len(draft.data_used) == 2


def test_r_ex_01_streak_is_broken_by_a_done_day():
    from server.rules.base import RuleContext
    from server.rules.r_ex_01_missed_exercise import MissedExerciseRule

    _delete("exercise_logs")
    db.insert("exercise_logs", {"id": "exl-d", "plan_id": "ex-141", "ts": iso(utcnow()), "status": "done",
                                "reason": None, "alternative_id": None})
    assert MissedExerciseRule().evaluate(RuleContext()) is None  # only day 140 is missed


def test_r_ex_01_ignores_today():
    from server.rules.base import RuleContext
    from server.rules.r_ex_01_missed_exercise import MissedExerciseRule

    _delete("exercise_logs")
    db.insert("exercise_logs", {"id": "exl-p", "plan_id": "ex-140", "ts": iso(utcnow()), "status": "done",
                                "reason": None, "alternative_id": None})
    # day 141 not logged, day 140 done, today (142) not logged yet: one missed day only
    assert MissedExerciseRule().evaluate(RuleContext()) is None
