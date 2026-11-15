"""Digital twin aggregator (owner: Shahd): GET /api/twin/state and GET /api/twin/timeline.

Covers the status mapping per region, "nodata" when a source is missing, one timeline entry per
mission day, the radiation estimate label, and that private check-in notes never leak.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import Alert
from server.features.monitoring.router import BodySystem, LatestReading, RadiationEstimate
from server.features.twin import service
from server.features.twin.models import ESTIMATE_LABEL, NO_DATA, REGION_IDS

STATUSES = {"ok", "watch", "review", "urgent", "nodata"}


def _alert(rule_id: str, level: str = "review", sources: list[str] | None = None) -> Alert:
    return Alert(id=f"al-{rule_id}", rule_id=rule_id, level=level, ts=iso(utcnow()), title=rule_id,
                 what_changed="test", sources=sources or [])


def _tile(id_: str, status: str, text: str = "x") -> BodySystem:
    return BodySystem(id=id_, status=status, text=text)


def _region(state: dict, rid: str) -> dict:
    return next(r for r in state["regions"] if r["id"] == rid)


# ---- live state ---------------------------------------------------------------------
def test_state_has_every_region_in_order(client):
    state = client.get("/api/twin/state").json()
    assert [r["id"] for r in state["regions"]] == list(REGION_IDS)
    assert state["simulated"] is True
    assert state["missionDay"] == client.get("/api/status").json()["missionDay"]
    assert state["disclaimer"] == "Visual summary. Not a medical device."
    for r in state["regions"]:
        assert r["status"] in STATUSES
        assert r["headline"]
        assert r["route"].startswith("/")
        for v in r["values"]:
            assert set(v) >= {"label", "value", "unit"}


def test_demo_brain_is_review_with_the_fatigue_alert(client):
    state = client.get("/api/twin/state").json()
    brain = _region(state, "brain")
    open_ids = {a["ruleId"]: a["id"] for a in client.get("/api/alerts").json() if a["status"] != "closed"}
    if "R-FAT-01" not in open_ids:
        pytest.skip("R-FAT-01 was closed by another test")
    assert brain["status"] == "review"
    assert "R-FAT-01" in brain["alerts"]
    assert any(ref["id"] == open_ids["R-FAT-01"] for ref in brain["alertRefs"])
    assert "possible" in brain["headline"].lower()
    titles = {s["id"] for s in brain["sourceTitles"]}
    assert {"nasa-hrp-sleep-risk", "nasa-pvt-iss"} <= titles


def test_brain_status_mapping():
    tiles = {"sleep": _tile("sleep", "stable", "Sleep in range"), "cognition": _tile("cognition", "stable", "reaction +1 %")}
    assert service._live_brain(tiles, []).status == "ok"
    assert service._live_brain(tiles, [_alert("R-SLP-01", "info")]).status == "watch"
    assert service._live_brain(tiles, [_alert("R-SLP-01", "info"), _alert("R-FAT-01")]).status == "review"
    nodata = {"sleep": _tile("sleep", "no_data"), "cognition": _tile("cognition", "no_data")}
    r = service._live_brain(nodata, [])
    assert r.status == "nodata" and r.headline == NO_DATA


def test_alert_status_mapping():
    assert service.alert_status(_alert("R-FAT-01")) == "review"
    assert service.alert_status(_alert("R-SLP-01", "info")) == "watch"
    assert service.alert_status(_alert("R-EX-01", "info")) == "review"  # same as the Bone & muscle tile
    assert service.alert_status(_alert("R-VIS-01", "info")) == "review"
    assert service.alert_status(_alert("R-SPO2-01", "urgent")) == "urgent"
    assert service.alert_status(_alert("R-SPO2-01", "info")) == "watch"
    assert service.alert_status(_alert("R-DATA-01", "info")) is None  # explains missing data only
    assert service.alert_status(_alert("R-NEW-99", "urgent")) == "urgent"
    assert service.worst("nodata", "ok", "watch") == "watch"
    assert service.worst() == "nodata"


def test_heart_has_no_rhythm_and_no_pulse_without_recent_data():
    stale = LatestReading(metric="heart_rate", reading=None, quality="missing")
    r = service._live_heart(_tile("cardiovascular", "no_data"), stale, [])
    assert r.status == "nodata" and r.pulse_bpm is None and r.headline.startswith("No recent data")
    rhythm = next(v for v in r.values if v.label == "Rhythm")
    assert rhythm.value is None  # no ECG sensor in the app


def test_heart_pulses_at_the_latest_reading(client):
    heart = _region(client.get("/api/twin/state").json(), "heart")
    latest = next(x for x in client.get("/api/readings/latest").json() if x["metric"] == "heart_rate")
    if latest["quality"] in ("good", "low"):
        assert heart["pulseBpm"] == round(latest["reading"]["value"])
    else:
        assert heart["pulseBpm"] is None and heart["status"] == "nodata"


def test_radiation_is_an_estimate_and_nodata_without_sourced_values(monkeypatch):
    r = service.radiation_region(142)
    assert r.estimate is True and ESTIMATE_LABEL in r.headline
    assert all(v.quality in (None, "estimate") for v in r.values)
    monkeypatch.setattr(service, "radiation_estimate", lambda day: RadiationEstimate(available=False, mission_day=day))
    r = service.radiation_region(142)
    assert r.status == "nodata" and r.headline == NO_DATA
    assert r.values[0].value is None


def test_eyes_nodata_without_any_self_check(monkeypatch):
    from server.features.monitoring import vision

    monkeypatch.setattr(vision, "list_checks", lambda n=None, until=None: [])
    r = service._live_eyes(utcnow(), [])
    assert r.status == "nodata"
    assert r.values[0].value is None


def test_sensors_come_from_get_sensors_with_real_locations(client):
    sensors = _region(client.get("/api/twin/state").json(), "sensors")["sensors"]
    api = {s["id"]: s for s in client.get("/api/sensors").json()}
    assert {s["id"] for s in sensors} <= set(api)
    assert "s-cabin" not in {s["id"] for s in sensors}  # habitat monitor is not a body sensor
    names = " ".join(s["name"].lower() for s in sensors)
    assert "dosimeter" not in names and "actigraph" not in names
    anchors = {s["id"]: s["anchor"] for s in sensors}
    assert anchors.get("s-chest") == "chest"
    assert anchors.get("s-skin") == "upperArm"
    assert anchors.get("s-wrist") == "leftWrist"
    assert anchors.get("s-bp") is None  # in the medical kit, not on the body
    for s in sensors:
        assert s["status"] == api[s["id"]]["status"]


def test_sensors_region_nodata_and_watch():
    from server.features.twin.models import TwinSensor

    def s(status: str) -> TwinSensor:
        return TwinSensor(id=f"s-{status}", name=status, location="Torso", status=status, last_seen=iso(utcnow()))

    assert service.sensors_region([]).status == "nodata"
    assert service.sensors_region([s("connected")]).status == "ok"
    down = service.sensors_region([s("connected"), s("disconnected")])
    assert down.status == "watch" and down.headline == "1 disconnected"


def test_temperature_disconnected_is_nodata_not_stable(client):
    temp = _region(client.get("/api/twin/state").json(), "temperature")
    patch = next(s for s in client.get("/api/sensors").json() if s["id"] == "s-skin")
    if patch["status"] == "disconnected":
        assert temp["status"] == "nodata"
        assert "Sensor disconnected" in temp["headline"]


# ---- timeline -------------------------------------------------------------------------
def test_timeline_returns_one_entry_per_day(client):
    today = client.get("/api/status").json()["missionDay"]
    tl = client.get(f"/api/twin/timeline?from={today - 13}&to={today}").json()
    days = [d["missionDay"] for d in tl["days"]]
    assert days == list(range(today - 13, today + 1))
    assert tl["today"] == today
    assert [d["isToday"] for d in tl["days"]] == [False] * 13 + [True]
    for d in tl["days"]:
        assert [r["id"] for r in d["regions"]] == list(REGION_IDS)
        rad = _region(d, "radiation")
        assert rad["estimate"] is True and ESTIMATE_LABEL in rad["headline"]


def test_timeline_default_range_and_validation(client):
    tl = client.get("/api/twin/timeline").json()
    assert len(tl["days"]) == 14 and tl["toDay"] == tl["today"]
    assert client.get("/api/twin/timeline?from=140&to=130").status_code == 422
    capped = client.get(f"/api/twin/timeline?from={tl['today'] - 1}&to={tl['today'] + 5}").json()
    assert capped["toDay"] == tl["today"]  # no future days


def test_timeline_has_no_invented_values_before_the_data(client):
    """A day before any stored data: everything is nodata except the radiation estimate."""
    today = client.get("/api/status").json()["missionDay"]
    day = today - 30
    tl = client.get(f"/api/twin/timeline?from={day}&to={day}").json()
    regions = {r["id"]: r for r in tl["days"][0]["regions"]}
    for rid in ("brain", "eyes", "heart", "lungs", "bones", "temperature", "sensors"):
        assert regions[rid]["status"] == "nodata", rid
        assert regions[rid]["pulseBpm"] is None
    measured = [v for rid in ("heart", "lungs", "temperature") for v in regions[rid]["values"]]
    assert all(v["value"] is None for v in measured)
    assert regions["radiation"]["status"] == "ok"  # estimate from the mission day, labelled as such


def test_timeline_sensors_have_no_history_and_rising_dose(client):
    tl = client.get("/api/twin/timeline").json()
    past = [d for d in tl["days"] if not d["isToday"]]
    assert all(_region(d, "sensors")["status"] == "nodata" for d in past)
    doses = [_region(d, "radiation")["values"][0]["value"] for d in tl["days"]]
    assert doses == sorted(doses) and doses[0] < doses[-1]


def test_timeline_brain_turns_review_with_the_short_nights(client):
    tl = client.get("/api/twin/timeline").json()
    by_day = {d["missionDay"]: _region(d, "brain")["status"] for d in tl["days"] if not d["isToday"]}
    today = tl["today"]
    early = [s for d, s in by_day.items() if d <= today - 3]
    assert early and all(s == "ok" for s in early)
    assert by_day[today - 1] in ("watch", "review")  # one short night + slower test by then


def test_timeline_is_read_only(client):
    before = db.count("alerts")
    client.get("/api/twin/timeline")
    client.get("/api/twin/state")
    assert db.count("alerts") == before


# ---- privacy ---------------------------------------------------------------------------
def test_private_checkin_notes_never_appear(client):
    secret = "PRIVATE-NOTE-twin-test-7f3a"
    db.insert("checkins", {"id": "ci-twin-private", "ts": iso(utcnow() - timedelta(days=20)), "mood": 3,
                           "stress": 2, "note_private": secret, "skipped": False})
    try:
        for path in ("/api/twin/state", "/api/twin/timeline"):
            text = client.get(path).text
            assert secret not in text
            assert "notePrivate" not in text and "note_private" not in text
    finally:
        with db.connect() as conn:
            conn.execute("DELETE FROM checkins WHERE id = 'ci-twin-private'")
