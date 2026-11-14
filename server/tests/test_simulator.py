"""The simulated data must contain the demo scenario."""
from datetime import timedelta

import numpy as np
import pytest

from server.core.config import parse_ts, utcnow
from server.core.simulator import generate


@pytest.fixture(scope="module")
def data():
    now = utcnow()
    return now, generate(now)


def test_everything_is_simulated(data):
    _, d = data
    for table in ("readings", "cabin_readings", "sleep_sessions"):
        assert d[table] and all(r["source"] == "simulated" for r in d[table]), table


def test_fourteen_days(data):
    _, d = data
    assert len(d["sleep_sessions"]) == 14
    assert len(d["cognitive_tests"]) == 14


def test_last_two_nights_short(data):
    _, d = data
    *rest, n141, n142 = d["sleep_sessions"]
    assert 270 <= n141["duration_min"] <= 330
    assert 270 <= n142["duration_min"] <= 330
    assert all(s["duration_min"] > 360 for s in rest)


def test_attention_twenty_percent_slower(data):
    _, d = data
    base = d["profiles"][0]["baseline"]["pvt_median_ms"]["mean"]
    for t in d["cognitive_tests"][-2:]:
        assert 0.15 <= t["median_ms"] / base - 1 <= 0.25


def test_skin_temp_stale_and_sensor_disconnected(data):
    now, d = data
    last = max(parse_ts(r["ts"]) for r in d["readings"] if r["metric"] == "skin_temp")
    assert timedelta(hours=5, minutes=50) <= now - last <= timedelta(hours=6, minutes=10)
    skin = next(s for s in d["sensors"] if "skin_temp" in s["metrics"])
    assert skin["status"] == "disconnected"


def test_no_blood_pressure_today(data):
    now, d = data
    # mission day 142 started 07:31 before "now"
    day_start = now - timedelta(hours=7, minutes=31)
    assert not [r for r in d["readings"] if r["metric"].startswith("bp_") and parse_ts(r["ts"]) >= day_start]


def test_resources_scenario(data):
    _, d = data
    res = d["resources"]
    assert len([r for r in res if r["kind"] == "medicine"]) >= 15
    assert len([r for r in res if r["kind"] == "equipment"]) >= 8
    assert any(r["status"] == "out_of_stock" for r in res)
    assert any(r["status"] == "expired" for r in res)
    allergies = set(d["profiles"][0]["allergies"])
    assert any(allergies & set(r["contraindicated_allergies"]) for r in res)


def test_baseline_present(data):
    _, d = data
    b = d["profiles"][0]["baseline"]["heart_rate"]
    assert 50 < b["mean"] < 90 and b["sd"] > 0 and b["n"] > 100
    assert np.isfinite(b["sd"])
