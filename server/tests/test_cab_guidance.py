"""Cabin "what to do" guidance (server/features/monitoring/cabin_guidance.py), R-CAB-02 (temperature /
humidity), R-CAB-03 (noise) and the guidance on GET /cabin/latest.

Limits come from config/thresholds.yaml: comfort zone [V2 6013] 20–25 °C / 30–60 %, crew-health
limit [V2 6012] 18–27 °C / 25–75 %, noise = mean + 2 SD of the last 7 days (team decision).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.core import db
from server.core.config import ROOT, iso, utcnow
from server.features.monitoring import cabin_guidance
from server.rules.base import RuleContext
from server.rules.r_cab_01_co2 import CabinCo2Rule
from server.rules.r_cab_02_temp_humidity import CabinTempHumidityRule
from server.rules.r_cab_03_noise import CabinNoiseRule

UNITS = {"co2": "mmHg", "cabin_temp": "°C", "humidity": "%", "noise": "dBA"}
MEDICATION = re.compile(
    r"medic|medicine|drug|dose|dosage|tablet|pill|capsule|analgesic|ibuprofen|paracetamol|acetaminophen"
    r"|aspirin|antihistamin|melatonin|supplement|prescri",
    re.I,
)


def _r(metric: str, value: float, minutes_ago: float) -> dict:
    return {"id": db.new_id(f"c-{metric}-test"), "metric": metric, "value": value, "unit": UNITS[metric],
            "ts": iso(utcnow() - timedelta(minutes=minutes_ago)), "source": "simulated"}


@contextmanager
def _only(metric: str, readings: list[dict]):
    """Replace all cabin readings of `metric` with `readings` for the test, then restore."""
    saved = db.query("cabin_readings", "metric = ?", (metric,))
    with db.connect() as conn:
        conn.execute("DELETE FROM cabin_readings WHERE metric = ?", (metric,))
    if readings:
        db.insert_many("cabin_readings", readings)
    try:
        yield
    finally:
        with db.connect() as conn:
            conn.execute("DELETE FROM cabin_readings WHERE metric = ?", (metric,))
        if saved:
            db.insert_many("cabin_readings", saved)


def _noise_history(latest: float) -> list[dict]:
    # 7 days of readings alternating 50 / 52 dBA (mean 51, SD ~1), then `latest` now.
    return [_r("noise", 50 + 2 * (i % 2), 60 * 6 * (i + 1)) for i in range(28)] + [_r("noise", latest, 1)]


def _all_steps_text(draft) -> str:
    return " ".join(s.text for s in draft.next_steps)


# ---- guidance content ------------------------------------------------------
def test_guidance_steps_are_operational_with_known_sources_and_resources():
    inventory = json.loads((ROOT / "data/simulated/resources.json").read_text(encoding="utf-8"))["resources"]
    ids = {r["id"] for r in inventory}
    for key, steps in cabin_guidance.GUIDANCE.items():
        assert steps, key
        for s in steps:
            assert s.source in cabin_guidance.SOURCES, (key, s)
            assert not MEDICATION.search(s.text), (key, s.text)
            assert not re.search(r"\d", s.text), (key, s.text)  # no numbers: limits live in thresholds.yaml
            if s.resource_id is not None:
                assert s.resource_id in ids, f"{key}: {s.resource_id} is not in resources.json"
    for text in cabin_guidance.SOURCES.values():
        assert not MEDICATION.search(text)


def test_co2_guidance_matches_the_requested_steps():
    assert [s.text for s in cabin_guidance.steps("co2_high")] == [
        "Confirm with a portable CO₂ reading",
        "Inform the crew member responsible for life support",
        "Move to a better-ventilated module",
        "Postpone strenuous exercise for now (exercise raises CO₂ output)",
        "Log any headache in today's check-in",
    ]
    exercise = cabin_guidance.steps("co2_high")[3]
    assert "ECLSS" in cabin_guidance.SOURCES[exercise.source]


def test_earplugs_and_co2_monitor_are_linked_simulated_equipment():
    inventory = json.loads((ROOT / "data/simulated/resources.json").read_text(encoding="utf-8"))["resources"]
    by_id = {r["id"]: r for r in inventory}
    assert by_id["eq-earplugs"]["name"] == "Earplugs" and by_id["eq-earplugs"]["kind"] == "equipment"
    assert by_id["eq-earplugs"]["status"] == "available" and by_id["eq-earplugs"]["qty"] > 0
    assert by_id["eq-co2-monitor"]["name"] == "Portable CO2 monitor" and by_id["eq-co2-monitor"]["kind"] == "equipment"
    assert by_id["eq-co2-monitor"]["status"] == "available" and by_id["eq-co2-monitor"]["qty"] == 1

    earplugs = next(s for s in cabin_guidance.steps("noise_high") if "earplugs" in s.text.lower())
    assert earplugs.resource_id == "eq-earplugs"
    confirm = cabin_guidance.steps("co2_high")[0]
    assert confirm.text == "Confirm with a portable CO₂ reading" and confirm.resource_id == "eq-co2-monitor"
    linked = {s.resource_id for steps in cabin_guidance.GUIDANCE.values() for s in steps} - {None}
    assert linked == {"eq-earplugs", "eq-co2-monitor"}


def test_exercise_step_cites_eclss_v2_7041():
    exercise = cabin_guidance.steps("co2_high")[3]
    text = cabin_guidance.SOURCES[exercise.source]
    assert "OCHMO-TB-002 Rev B" in text and "[V2 7041]" in text
    assert "exercise increases CO₂, perspiration and metabolic heat output" in text
    assert text in CabinCo2Rule.sources


# ---- R-CAB-01 reuses the CO2 guidance ------------------------------------------
def test_r_cab_01_uses_the_shared_co2_steps(client):
    with _only("co2", [_r("co2", 4.0, 10), _r("co2", 5.0, 20)]):
        draft = CabinCo2Rule().evaluate(RuleContext())
    texts = [s.text for s in draft.next_steps]
    assert texts[:-1] == [s.text for s in cabin_guidance.steps("co2_high")]
    assert texts[-1] == "Add this alert to the report"
    assert not MEDICATION.search(_all_steps_text(draft))
    assert any("ECLSS" in s for s in CabinCo2Rule.sources)


# ---- R-CAB-02 --------------------------------------------------------------------
@pytest.mark.parametrize("metric,value,level", [
    ("cabin_temp", 26.0, "info"),     # outside 20–25 comfort, inside 18–27 health
    ("cabin_temp", 19.0, "info"),
    ("cabin_temp", 28.0, "review"),   # outside 18–27 health limit
    ("cabin_temp", 17.0, "review"),
    ("humidity", 65.0, "info"),       # outside 30–60 comfort, inside 25–75 health
    ("humidity", 28.0, "info"),
    ("humidity", 80.0, "review"),     # outside 25–75 health limit
    ("humidity", 20.0, "review"),
])
def test_r_cab_02_fires_at_the_right_level(client, metric, value, level):
    other = "humidity" if metric == "cabin_temp" else "cabin_temp"
    normal = {"cabin_temp": 22.0, "humidity": 45.0}[other]
    with _only(metric, [_r(metric, value, 5)]), _only(other, [_r(other, normal, 5)]):
        draft = CabinTempHumidityRule().evaluate(RuleContext())
    assert draft is not None and draft.level == level
    assert draft.dedupe_key == "cab-temp-humidity"
    # the 5 sections
    assert "comfort zone" in draft.what_changed and "[V2 6013]" in draft.what_changed
    assert ("[V2 6012]" in draft.what_changed) == (level == "review")
    assert len(draft.data_used) == 1
    assert draft.missing == []
    assert draft.possible_factors and all("possible link, not a confirmed cause" in f for f in draft.possible_factors)
    key = "temperature_out" if metric == "cabin_temp" else "humidity_out"
    assert [s.text for s in draft.next_steps][:-1] == [s.text for s in cabin_guidance.steps(key)]
    assert not MEDICATION.search(_all_steps_text(draft))
    assert any("[V2 6013]" in s for s in draft.sources) and any("[V2 6012]" in s for s in draft.sources)
    assert "cause" not in draft.what_changed.lower()


def test_r_cab_02_inside_the_comfort_zone_does_not_fire(client):
    with _only("cabin_temp", [_r("cabin_temp", 22.5, 5)]), _only("humidity", [_r("humidity", 45.0, 5)]):
        assert CabinTempHumidityRule().evaluate(RuleContext()) is None


def test_r_cab_02_ignores_stale_readings(client):
    with _only("cabin_temp", [_r("cabin_temp", 30.0, 180)]), _only("humidity", [_r("humidity", 45.0, 5)]):
        assert CabinTempHumidityRule().evaluate(RuleContext()) is None


def test_r_cab_02_both_out_is_one_alert_with_the_higher_level_and_no_repeated_step(client):
    with _only("cabin_temp", [_r("cabin_temp", 26.0, 5)]), _only("humidity", [_r("humidity", 80.0, 5)]):
        draft = CabinTempHumidityRule().evaluate(RuleContext())
    assert draft.level == "review"
    assert "temperature" in draft.what_changed and "humidity" in draft.what_changed
    texts = [s.text for s in draft.next_steps]
    assert texts.count("Inform the crew member responsible for life support") == 1
    assert "Adjust clothing layers" in texts and "Log any dry eyes or dry skin in today's check-in" in texts


# ---- R-CAB-03 --------------------------------------------------------------------
def test_r_cab_03_noise_above_the_7_day_average_fires_info(client):
    with _only("noise", _noise_history(60.0)):
        draft = CabinNoiseRule().evaluate(RuleContext())
    assert draft is not None and draft.level == "info"
    assert draft.dedupe_key == "cab-noise-high"
    assert "7-day cabin average" in draft.what_changed and "team decision" in draft.what_changed
    assert draft.data_used and draft.missing and draft.possible_factors
    assert all("possible link, not a confirmed cause" in f for f in draft.possible_factors)
    assert [s.text for s in draft.next_steps][:-1] == [s.text for s in cabin_guidance.steps("noise_high")]
    assert not MEDICATION.search(_all_steps_text(draft))
    assert draft.sources == [] and CabinNoiseRule.sources[0].startswith("Team decision")


@pytest.mark.parametrize("latest", [51.0, 40.0])  # usual, and low (low noise needs no action)
def test_r_cab_03_usual_or_low_noise_does_not_fire(client, latest):
    with _only("noise", _noise_history(latest)):
        assert CabinNoiseRule().evaluate(RuleContext()) is None


def test_noise_is_team_decision_in_thresholds(client):
    t = RuleContext().thresholds
    assert t["noise_sd_multiplier"].source.lower().startswith("team decision")
    assert t["noise_baseline_days"].source.lower().startswith("team decision")


# ---- engine + Today tile -----------------------------------------------------------
@pytest.fixture
def fresh_db():
    from server.core.seed import seed

    old = os.environ.get("ASTROCARE_DB_PATH")
    os.environ["ASTROCARE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="astrocare-cabguide-")) / "g.db")
    try:
        seed(utcnow(), force=True)
        yield
    finally:
        if old is None:
            os.environ.pop("ASTROCARE_DB_PATH", None)
        else:
            os.environ["ASTROCARE_DB_PATH"] = old


def _open(rule_id: str) -> list[dict]:
    return db.query("alerts", "rule_id = ? AND status != 'closed'", (rule_id,))


def _tile(c, metric: str) -> dict:
    return next(e for e in c.get("/api/cabin/latest").json() if e["metric"] == metric)


def test_reseed_state_has_no_cabin_alerts_and_no_tile_guidance(fresh_db):
    from server.main import app
    from server.rules.engine import run_rules

    run_rules()
    for rule in ("R-CAB-01", "R-CAB-02", "R-CAB-03"):
        assert _open(rule) == [], rule
    c = TestClient(app)
    for e in c.get("/api/cabin/latest").json():
        assert e["status"] == "usual" and e["guidance"] == [] and e["alertId"] is None, e


def test_one_open_alert_per_rule_and_the_tile_links_it(fresh_db):
    from server.main import app
    from server.rules.engine import run_rules

    db.insert("cabin_readings", _r("cabin_temp", 26.0, 0))
    db.insert("cabin_readings", _r("noise", 90.0, 0))
    run_rules()
    run_rules()
    (temp_alert,) = _open("R-CAB-02")
    (noise_alert,) = _open("R-CAB-03")
    assert temp_alert["level"] == "info" and noise_alert["level"] == "info"

    c = TestClient(app)
    temp = _tile(c, "cabin_temp")
    assert temp["status"] == "above_usual" and temp["alertId"] == temp_alert["id"]
    assert [s["text"] for s in temp["guidance"]] == [s.text for s in cabin_guidance.steps("temperature_out")]
    assert all(s["source"] in cabin_guidance.SOURCES.values() for s in temp["guidance"])
    noise = _tile(c, "noise")
    assert noise["alertId"] == noise_alert["id"]
    earplugs = next(s for s in noise["guidance"] if "earplugs" in s["text"].lower())
    assert (earplugs["resourceId"], earplugs["availability"], earplugs["lockedForCMO"]) == ("eq-earplugs", "available", False)
    # normal tiles stay as they are
    for metric in ("co2", "humidity"):
        e = _tile(c, metric)
        assert e["status"] == "usual" and e["guidance"] == [] and e["alertId"] is None


def test_tile_steps_are_resource_checked(fresh_db, monkeypatch):
    from server.main import app

    steps = (
        cabin_guidance.GuidanceStep("Check the reading with the digital thermometer", "team-decision",
                                    resource_id="eq-thermometer"),
        cabin_guidance.GuidanceStep("Use the item that is not onboard", "team-decision", resource_id="eq-nothing"),
    )
    monkeypatch.setitem(cabin_guidance.GUIDANCE, "temperature_out", steps)
    db.insert("cabin_readings", _r("cabin_temp", 26.0, 0))
    guidance = _tile(TestClient(app), "cabin_temp")["guidance"]
    assert [(s["resourceId"], s["availability"], s["lockedForCMO"]) for s in guidance] == [
        ("eq-thermometer", "available", False),
        ("eq-nothing", "out_of_stock", False),
    ]


def test_alert_steps_are_resource_checked_by_the_engine(fresh_db, monkeypatch):
    from server.rules.engine import run_rules

    steps = (cabin_guidance.GuidanceStep("Check the reading with the digital thermometer", "team-decision",
                                         resource_id="eq-thermometer"),)
    monkeypatch.setitem(cabin_guidance.GUIDANCE, "humidity_out", steps)
    db.insert("cabin_readings", _r("humidity", 65.0, 0))
    run_rules()
    (alert,) = _open("R-CAB-02")
    first = alert["next_steps"][0]
    assert first["resource_id"] == "eq-thermometer" and first["availability"] == "available"


def test_a_day_of_live_feed_never_triggers_the_cabin_rules(fresh_db):
    from server.core import live_feed
    from server.rules.engine import run_rules

    t = utcnow()
    for i in range(4 * 24):  # one day of cabin ticks, every 15 min
        t += timedelta(minutes=15)
        live_feed.tick(t)
        if i % 8 == 0:
            ctx = RuleContext(now=t)
            assert CabinCo2Rule().evaluate(ctx) is None
            assert CabinTempHumidityRule().evaluate(ctx) is None
            assert CabinNoiseRule().evaluate(ctx) is None
    run_rules(RuleContext(now=t))
    for rule in ("R-CAB-01", "R-CAB-02", "R-CAB-03"):
        assert _open(rule) == [], rule
