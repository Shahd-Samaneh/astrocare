"""Tests for GET /api/body-systems (the Today-screen body-systems tiles)."""
from __future__ import annotations

from server.core import db

ORDER = [
    "cardiovascular", "respiratory", "sleep", "cognition",
    "bone_muscle", "radiation", "vision", "thermoregulation",
]


def _systems(client) -> dict:
    return {s["id"]: s for s in client.get("/api/body-systems").json()}


def test_order_and_shape(client):
    data = client.get("/api/body-systems").json()
    assert [s["id"] for s in data] == ORDER
    for s in data:
        assert set(s) >= {"id", "status", "text", "alertId"}
        assert s["status"] in {"stable", "review", "no_data"}
        assert s["text"]  # never empty


def test_stable_systems(client):
    s = _systems(client)
    assert s["cardiovascular"]["status"] == "stable"
    assert "HR" in s["cardiovascular"]["text"]
    assert s["respiratory"]["status"] == "stable"
    assert "SpO₂" in s["respiratory"]["text"]
    # bone_muscle: counts for past days only (today excluded) -> "1 done, 1 partial this week"
    assert s["bone_muscle"]["status"] == "stable"
    assert s["bone_muscle"]["text"] == "1 done, 1 partial this week"
    assert "%" not in s["bone_muscle"]["text"]  # no percentage, per spec


def test_bone_muscle_uses_latest_log_once_per_planned_session(client):
    # A newer skipped log replaces the seeded completion for day 140. It changes
    # the strict-majority outcome, and must not be counted alongside the old log.
    db.insert("exercise_logs", {
        "id": "exl-bone-newer-skip", "plan_id": "ex-140", "ts": "2099-01-01T00:00:00Z",
        "status": "skipped", "reason": "time", "alternative_id": None,
    })
    assert client.get("/api/exercise/plan?day=140").json()[0]["log"]["status"] == "skipped"
    bone = _systems(client)["bone_muscle"]
    assert bone["status"] == "review"
    assert bone["text"] == "0 done, 1 partial this week"

    # A still newer done log changes the same planned session back to complete.
    db.insert("exercise_logs", {
        "id": "exl-bone-newer-done", "plan_id": "ex-140", "ts": "2100-01-01T00:00:00Z",
        "status": "done", "reason": None, "alternative_id": None,
    })
    assert client.get("/api/exercise/plan?day=140").json()[0]["log"]["status"] == "done"
    bone = _systems(client)["bone_muscle"]
    assert bone["status"] == "stable"
    assert bone["text"] == "1 done, 1 partial this week"


def test_review_systems(client):
    s = _systems(client)
    assert s["sleep"]["status"] == "review"
    assert s["sleep"]["text"] == "2 short nights"
    assert s["cognition"]["status"] == "review"
    assert "reaction" in s["cognition"]["text"] and "%" in s["cognition"]["text"]


def test_no_data_systems(client):
    s = _systems(client)
    for sysid in ("radiation", "vision"):
        assert s[sysid]["status"] == "no_data"
        assert s[sysid]["text"] == "No connected measurements"
    # skin patch is disconnected in the seed -> no_data with the sensor status
    assert s["thermoregulation"]["status"] == "no_data"
    assert "disconnected" in s["thermoregulation"]["text"]


def test_thermoregulation_links_rdata_alert_but_stays_no_data(client):
    s = _systems(client)
    thermo = s["thermoregulation"]
    assert thermo["status"] == "no_data"  # R-DATA-01 never forces review
    rdata = next(a for a in client.get("/api/alerts").json() if a["ruleId"].startswith("R-DATA-"))
    assert thermo["alertId"] == rdata["id"]  # linked for explanation


def test_open_alert_forces_review(client):
    # An open alert mapped to a system (not R-DATA-*) forces review + alertId.
    db.insert("alerts", {
        "id": "al-hr-test", "rule_id": "R-HR-01", "level": "review", "ts": "2026-11-14T00:00:00Z",
        "title": "HR test", "what_changed": "test", "data_used": [], "missing": [],
        "possible_factors": [], "next_steps": [], "status": "new", "sources": [],
    })
    try:
        cardio = _systems(client)["cardiovascular"]
        assert cardio["status"] == "review"
        assert cardio["alertId"] == "al-hr-test"
    finally:
        from server.core.db import connect

        with connect() as conn:
            conn.execute("DELETE FROM alerts WHERE id = ?", ("al-hr-test",))
