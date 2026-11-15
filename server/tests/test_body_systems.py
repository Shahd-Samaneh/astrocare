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


def test_review_systems(client):
    s = _systems(client)
    assert s["sleep"]["status"] == "review"
    assert s["sleep"]["text"] == "2 short nights"
    assert s["cognition"]["status"] == "review"
    assert "reaction" in s["cognition"]["text"] and "%" in s["cognition"]["text"]


def test_radiation_is_a_simulated_estimate_within_limit(client):
    rad = _systems(client)["radiation"]
    day = client.get("/api/status").json()["missionDay"]
    dose = int(day * 1.8 + 0.5)
    assert rad["status"] == "stable"
    assert rad["statusLabel"] == "within limit"
    assert rad["simulated"] is True
    assert rad["text"] == f"{dose} mSv · {int(dose_pct(day) + 0.5)}% of career limit (estimate)"
    assert rad["alertId"] is None


def dose_pct(day: int) -> float:
    return day * 1.8 / 600 * 100


def test_no_data_systems(client):
    s = _systems(client)
    assert s["vision"]["status"] == "no_data"
    assert s["vision"]["text"] == "No connected measurements"
    assert s["vision"]["simulated"] is False and s["vision"]["statusLabel"] is None
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
