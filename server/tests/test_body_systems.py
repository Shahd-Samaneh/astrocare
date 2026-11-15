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


def test_vision_tile_reflects_the_seeded_self_check(client):
    # No sensor: the tile comes from the seeded self-checks (days 130 + 137, no change).
    v = _systems(client)["vision"]
    assert v["status"] == "stable"
    assert v["text"] == "Self-check · last mission day 137"
    assert v["simulated"] is False and v["statusLabel"] == "no change vs baseline"


def test_no_data_systems(client):
    s = _systems(client)
    # skin patch is disconnected in the seed -> no_data, last value with its age, never "Stable"
    t = s["thermoregulation"]
    assert t["status"] == "no_data"
    assert t["text"] == "Last: 33.9 °C · 6 h ago"
    assert t["thermo"]["statusText"] == "Sensor disconnected"
    assert t["thermo"]["fresh"] is False and t["thermo"]["lastTs"]


def test_thermoregulation_cabin_context_uses_sourced_comfort_zone(client):
    thermo = _systems(client)["thermoregulation"]["thermo"]
    cabin_temp = next(e for e in client.get("/api/cabin/latest").json() if e["metric"] == "cabin_temp")
    limit = cabin_temp["limit"]  # same limit object the cabin tile shows
    assert thermo["cabin"] == (
        f"Cabin {round(cabin_temp['value'], 1):g} °C · comfort zone {limit['min']:g}–{limit['max']:g} °C "
        f"({limit['sourceLabel']})"
    )
    assert limit["sourceLabel"] == "NASA-STD-3001 [V2 6013]"
    assert thermo["cabinSource"] == limit["source"]


def test_thermoregulation_manual_entry_supported(client):
    assert _systems(client)["thermoregulation"]["thermo"]["manualEntry"] is True


def _with_skin_reading(client, value: float, quality: str = "good") -> dict:
    """Insert a fresh skin_temp reading, return the tile, then remove the reading again."""
    from server.core.config import iso, utcnow
    db.insert("readings", {
        "id": "r-skin-test", "astronaut_id": "c2", "metric": "skin_temp", "value": value,
        "unit": "°C", "ts": iso(utcnow()), "source": "manual", "quality": quality,
    })
    try:
        return _systems(client)["thermoregulation"]
    finally:
        with db.connect() as conn:
            conn.execute("DELETE FROM readings WHERE id = ?", ("r-skin-test",))


def _skin_baseline(client) -> dict:
    return client.get("/api/profile").json()["baseline"]["skin_temp"]


def test_thermoregulation_fresh_good_in_baseline_is_stable(client):
    t = _with_skin_reading(client, _skin_baseline(client)["mean"])
    assert t["status"] == "stable" and t["thermo"]["statusText"] == "Stable"
    assert t["thermo"]["fresh"] is True and t["text"].endswith("in baseline")


def test_thermoregulation_fresh_outside_baseline_is_review(client):
    b = _skin_baseline(client)
    t = _with_skin_reading(client, b["mean"] + 10 * b["sd"] + 1)
    assert t["status"] == "review" and t["thermo"]["statusText"] == "Review"


def test_thermoregulation_fresh_low_quality_is_not_stable(client):
    t = _with_skin_reading(client, _skin_baseline(client)["mean"], quality="low")
    assert t["status"] == "no_data" and t["thermo"]["statusText"] == "No data"


def test_thermoregulation_back_to_stale_after_test_reading(client):
    assert _systems(client)["thermoregulation"]["thermo"]["statusText"] == "Sensor disconnected"


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
