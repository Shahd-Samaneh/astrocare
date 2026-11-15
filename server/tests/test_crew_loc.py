# Owner: Shahd
"""R-LOC-01 (possible loss of consciousness) and the crew emergency flow.

Each test gets its own freshly seeded DB. Time is a fake clock: every function takes `now`,
and the API tests monkeypatch `store.clock`.
"""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

from server.core import db
from server.core.config import iso, utcnow


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setenv("ASTROCARE_DB_PATH", str(Path(tempfile.mkdtemp(prefix="astrocare-loc-")) / "loc.db"))
    from server.core.seed import seed

    seed(force=True)
    yield utcnow() + timedelta(minutes=1)  # "now" for the test, just after the seeded data


# ---- helpers ----------------------------------------------------------------------------
def _reading(now, secs_before, metric, value, quality="good"):
    unit = {"heart_rate": "bpm", "spo2": "%", "resp_rate": "/min"}[metric]
    return {"id": db.new_id(f"t-{metric}"), "astronaut_id": "c2", "metric": metric, "value": float(value),
            "unit": unit, "ts": iso(now - timedelta(seconds=secs_before)), "source": "simulated", "quality": quality}


def hr_stream(now, *, last_before=45, drop_to=None, quality="good", drop_quality=None):
    """HR every 10 s from -6 min to -last_before s at ~72 bpm, then optionally two readings at drop_to."""
    rows = [_reading(now, s, "heart_rate", 72, quality) for s in range(360, last_before - 1, -10)]
    if drop_to is not None:
        rows += [_reading(now, last_before - 10, "heart_rate", drop_to, drop_quality or quality),
                 _reading(now, last_before - 20, "heart_rate", drop_to, drop_quality or quality)]
    db.insert_many("readings", rows)


def motion(now, *, still_from=40, quality="good"):
    from server.features.crew import store

    store.add_motion([
        {"id": db.new_id("t-mot"), "astronaut_id": "c2", "sensor_id": "s-wrist", "ts": iso(now - timedelta(seconds=s)),
         "value_g": 0.15 if s > still_from else 0.01, "quality": quality, "source": "simulated"}
        for s in range(360, -1, -5)
    ])


def low_spo2(now, quality="good"):
    db.insert("readings", _reading(now, 15, "spo2", 85, quality))


def loc_alerts(now):
    from server.rules.base import RuleContext
    from server.rules.engine import run_rules

    return [a for a in run_rules(RuleContext(now=now)) if a.rule_id == "R-LOC-01"]


def kinds(now):
    from server.rules.base import RuleContext
    from server.rules.r_loc_01_possible_loc import find_signals

    return sorted(s.kind for s in find_signals(RuleContext(now=now), "c2", ignore_before=None)[0])


def demo(now):
    from server.features.crew import demo as crew_demo, store

    alert_id = crew_demo.trigger(now)
    assert alert_id
    em = next(e for e in store.listing(now)["open"] if e["alert_id"] == alert_id)
    return alert_id, em


def steps(em):
    return [s["step"] for s in em["timeline"]]


# ---- the rule -----------------------------------------------------------------------------
def test_seeded_data_alone_never_fires(fresh):
    assert kinds(fresh) == []
    assert loc_alerts(fresh) == []


def test_fires_on_two_of_four_signals(fresh):
    hr_stream(fresh, drop_to=40)  # HR drop, and the chest strap stops at -25 s -> chest gap
    assert kinds(fresh) == ["chest_gap", "hr_change"]
    [alert] = loc_alerts(fresh)
    assert alert.level == "urgent"
    assert alert.title == "Possible loss of consciousness: check crew member now"
    assert "Heart-rate change" in alert.what_changed and "Chest sensor signal lost" in alert.what_changed
    assert any("SpO" in m for m in alert.missing)  # no SpO2 in the last 60 s
    assert all("not confirmed" in f for f in alert.possible_factors)
    assert [s.locked_for_cmo for s in alert.next_steps] == [False, False, True]


def test_fires_on_no_motion_plus_low_spo2(fresh):
    motion(fresh)
    low_spo2(fresh)
    assert kinds(fresh) == ["low_spo2", "no_motion"]
    assert len(loc_alerts(fresh)) == 1


@pytest.mark.parametrize("make", [
    lambda now: hr_stream(now, last_before=0, drop_to=None) or db.insert_many(
        "readings", [_reading(now, 3, "heart_rate", 40)]),  # HR change, chest still streaming
    lambda now: hr_stream(now, last_before=30),              # chest gap only (no HR change)
    lambda now: motion(now),                                  # no motion only
    lambda now: low_spo2(now),                                # low SpO2 only
])
def test_one_signal_alone_does_not_fire(fresh, make):
    make(fresh)
    assert len(kinds(fresh)) == 1
    assert loc_alerts(fresh) == []


def test_low_quality_data_alone_never_fires(fresh):
    hr_stream(fresh, drop_to=40, quality="low")
    motion(fresh, quality="low")
    low_spo2(fresh, quality="low")
    assert kinds(fresh) == []
    assert loc_alerts(fresh) == []


def test_low_quality_drop_does_not_count(fresh):
    hr_stream(fresh, drop_to=40, drop_quality="low")  # good stream, the drop itself is low quality
    assert "hr_change" not in kinds(fresh)


def test_one_open_alert_per_crew_member_and_no_refire(fresh):
    alert_id, em = demo(fresh)
    assert loc_alerts(fresh + timedelta(seconds=5)) == []  # still open: no duplicate
    from server.features.crew import store

    store.respond(em["id"], fresh + timedelta(seconds=5))
    assert db.get("alerts", alert_id)["status"] == "closed"
    # the same signals are still inside the 60 s window, but they were already handled
    assert loc_alerts(fresh + timedelta(seconds=10)) == []


def test_never_says_fainted_or_gives_treatment(fresh):
    alert_id, em = demo(fresh)
    a = db.get("alerts", alert_id)
    text = " ".join([a["title"], a["what_changed"], *a["possible_factors"], *[s["text"] for s in a["next_steps"]],
                     *[s["text"] for s in em["timeline"]]]).lower()
    assert "faint" not in text and "syncope" not in text
    assert a["next_steps"][-1]["locked_for_cmo"] is True  # the only clinical step is CMO-locked


# ---- Watch -> "I'm OK" / escalation ---------------------------------------------------------
def test_demo_opens_a_watch_with_its_signals(fresh):
    _, em = demo(fresh)
    assert em["status"] == "watch"
    assert sorted(s["kind"] for s in em["signals"]) == ["chest_gap", "hr_change", "no_motion"]
    assert steps(em) == ["detected", "check_shown"]
    assert em["deadline_ts"] == iso(fresh + timedelta(seconds=30))


def test_crew_texts_carry_iso_times_alert_text_says_utc(fresh):
    import re

    alert_id, em = demo(fresh)
    iso_re = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    crew_text = " ".join([*(s["detail"] for s in em["signals"]), *em["missing"]])
    assert iso_re.search(crew_text) and "UTC" not in crew_text  # the page turns these into local time
    what = db.get("alerts", alert_id)["what_changed"]
    assert "UTC" in what and not iso_re.search(what)  # the alert (other pages) keeps labelled UTC times


def test_im_ok_cancels_escalation_and_closes_the_watch(fresh):
    from server.features.crew import store

    alert_id, em = demo(fresh)
    em = store.respond(em["id"], fresh + timedelta(seconds=7))
    assert em["status"] == "resolved" and em["outcome"] == "responded"
    assert steps(em)[-2:] == ["responded", "resolved"]
    assert db.get("alerts", alert_id)["status"] == "closed"
    later = store.listing(fresh + timedelta(seconds=60))
    assert later["open"] == []  # no escalation after the deadline
    assert [e["id"] for e in later["history"]] == [em["id"]]
    assert db.count("action_log", "action = 'crew_loc:responded' AND ref_id = ?", (em["id"],)) == 1


def test_no_response_escalates_after_30_s(fresh):
    from server.features.crew import store

    _, em = demo(fresh)
    assert store.listing(fresh + timedelta(seconds=29))["open"][0]["status"] == "watch"
    [em] = store.listing(fresh + timedelta(seconds=30))["open"]
    assert em["status"] == "emergency"
    assert steps(em) == ["detected", "check_shown", "no_response", "escalated"]  # no timeline row for the report
    assert em["report_note"] == "will be queued when reporting is available"
    assert db.count("action_log", "action = 'crew_loc:escalated'") == 1
    # the technical reason is only in the action log
    assert db.count("action_log", "action LIKE 'crew_loc:report_skipped:%sourceFeature%' AND ref_id = ?", (em["id"],)) == 1
    assert not any("docs/" in s["text"] or "API" in s["text"] for s in em["timeline"])


def test_late_im_ok_is_recorded_but_keeps_the_emergency_open(fresh):
    from server.features.crew import store

    _, em = demo(fresh)
    store.listing(fresh + timedelta(seconds=31))
    em = store.respond(em["id"], fresh + timedelta(seconds=40))
    assert em["status"] == "emergency" and steps(em)[-1] == "responded"


def test_ack_and_resolve_update_the_timeline(fresh):
    from server.features.crew import store

    alert_id, em = demo(fresh)
    store.listing(fresh + timedelta(seconds=31))
    em = store.ack(em["id"], "cmo", "On my way", fresh + timedelta(seconds=40))
    assert db.get("alerts", alert_id)["status"] == "ack"
    em = store.ack(em["id"], "commander", None, fresh + timedelta(seconds=45))
    em = store.ack(em["id"], "cmo", None, fresh + timedelta(seconds=46))  # twice: no second step
    em = store.resolve(em["id"], "sensor_issue", "Chest strap had come loose.", fresh + timedelta(seconds=90))
    assert steps(em) == ["detected", "check_shown", "no_response", "escalated",
                         "ack_cmo", "ack_commander", "resolved"]
    assert em["ack_cmo_ts"] == iso(fresh + timedelta(seconds=40))
    assert em["outcome"] == "sensor_issue" and em["status"] == "resolved"
    assert db.get("alerts", alert_id)["status"] == "closed"
    with pytest.raises(store.CrewError):
        store.resolve(em["id"], "other", "again", fresh + timedelta(seconds=95))


def test_report_item_created_on_escalation_when_the_api_takes_crew(fresh, monkeypatch):
    from server.features.crew import store
    from server.features.reports import service

    monkeypatch.setattr(store, "_reports_accept_crew", lambda: True)
    alert_id, em = demo(fresh)
    [em] = store.listing(fresh + timedelta(seconds=30))["open"]
    assert steps(em)[-1] == "report_queued"
    item = service.get_report_item(em["report_item_id"])
    assert item["kind"] == "note" and item["source_feature"] == "crew" and item["ref_id"] == alert_id
    assert "possible loss of consciousness" in item["title"]


def test_reports_api_today_does_not_take_crew(fresh):
    from server.features.crew import store

    assert store._reports_accept_crew() is False  # flips to True once Noura adds 'crew' (docs/proposals/loc.md)


def test_reseed_clears_all_watches_and_emergencies(fresh):
    from server.core.seed import seed
    from server.features.crew import store

    demo(fresh)
    store.listing(fresh + timedelta(seconds=31))  # one emergency
    seed(force=True)
    d = store.listing(utcnow())
    assert d["open"] == [] and d["history"] == []
    assert store.motion_samples("c2", fresh - timedelta(hours=1), fresh + timedelta(hours=1)) == []


# ---- API -----------------------------------------------------------------------------------
def test_api_flow(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from server.features.crew import store
    from server.main import app

    t = {"now": fresh}
    monkeypatch.setattr(store, "clock", lambda: t["now"])
    with TestClient(app) as c:
        r = c.post("/api/crew/demo/loc")
        assert r.status_code == 201, r.text
        em_id = r.json()["emergencyId"]
        assert c.post("/api/crew/demo/loc").status_code == 409  # one open event per crew member

        d = c.get("/api/crew/emergencies").json()
        assert d["demo"] is True and d["responseSeconds"] == 30
        assert d["open"][0]["status"] == "watch" and d["open"][0]["emergency"] is True
        assert d["open"][0]["alertLevel"] == "urgent"

        assert c.post(f"/api/crew/emergencies/{em_id}/ack", json={"role": "doctor"}).status_code == 422
        assert c.post(f"/api/crew/emergencies/{em_id}/resolve", json={"outcome": "other", "note": " "}).status_code == 422
        assert c.post("/api/crew/emergencies/nope/respond").status_code == 404

        t["now"] = fresh + timedelta(seconds=31)
        em = c.get("/api/crew/emergencies").json()["open"][0]
        assert em["status"] == "emergency" and em["acknowledged"] is False
        em = c.post(f"/api/crew/emergencies/{em_id}/ack", json={"role": "cmo"}).json()
        assert em["acknowledged"] is True and em["ackCmoTs"]
        em = c.post(f"/api/crew/emergencies/{em_id}/resolve",
                    json={"outcome": "medical_event", "note": "Assessed by the CMO."}).json()
        assert em["status"] == "resolved"
        assert c.post(f"/api/crew/emergencies/{em_id}/respond").status_code == 409
        assert c.get("/api/reports/items").status_code == 200  # the outbox list still works


def test_demo_endpoint_off_when_demo_false(fresh, monkeypatch):
    from fastapi.testclient import TestClient

    from server.features.crew import store
    from server.main import app

    monkeypatch.setattr(store, "demo_enabled", lambda: False)
    with TestClient(app) as c:
        assert c.post("/api/crew/demo/loc").status_code == 404
        assert c.get("/api/crew/emergencies").json()["demo"] is False


def test_loc_thresholds_have_source_and_note():
    from server.features.crew.thresholds import loc_entries

    entries = loc_entries()
    for key in ("window_seconds", "hr_change_pct", "signal_gap_seconds", "no_motion_seconds", "response_seconds"):
        assert key in entries
    assert entries["window_seconds"].value == 60 and entries["response_seconds"].value == 30
    for key, e in entries.items():
        assert e.source and e.note, key
        assert "experimental value" in e.note, key  # no published source for any of them
