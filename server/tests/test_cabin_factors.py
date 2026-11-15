"""Cabin conditions as a possible factor on R-FAT-01 / R-SLP-01 (server/rules/cabin_factors.py).

Each test gets its own freshly seeded throwaway DB (daily_client), so cabin rows can be
replaced freely. Seeded cabin CO₂ averages ~2.6 mmHg (above the 2.5 mmHg TB-004 value);
temperature and humidity stay inside their NASA-STD-3001 ranges.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from server.core import db
from server.core.config import Threshold, iso
from server.rules.base import RuleContext
from server.rules.cabin_factors import CO2_FACTOR, HUMIDITY_FACTOR, MAX_IDS, TEMP_FACTOR, cabin_factors
from server.rules.r_fat_01_fatigue_pattern import FatiguePatternRule
from server.rules.r_slp_01_short_sleep import ShortSleepRule
from server.tests._daily_helpers import daily_client, open_alert


@pytest.fixture
def c():
    with daily_client() as client:
        yield client


def _replace(metric: str, values_hours_ago: list[tuple[float, float]], unit: str) -> list[str]:
    from server.core.db import connect

    with connect() as conn:
        conn.execute("DELETE FROM cabin_readings WHERE metric = ?", (metric,))
    now = RuleContext().now
    rows = [{"id": f"cf-{metric}-{i}", "metric": metric, "value": v, "unit": unit,
             "ts": iso(now - timedelta(hours=h)), "source": "simulated"} for i, (v, h) in enumerate(values_hours_ago)]
    if rows:
        db.insert_many("cabin_readings", rows)
    return [r["id"] for r in rows]


def test_seeded_fatigue_and_sleep_alerts_list_the_co2_factor_and_its_data(c):
    for rule_id in ("R-FAT-01", "R-SLP-01"):
        a = open_alert(c, rule_id)
        assert CO2_FACTOR in a["possibleFactors"], rule_id
        assert TEMP_FACTOR not in a["possibleFactors"] and HUMIDITY_FACTOR not in a["possibleFactors"]
        assert any(x.startswith("Cabin CO₂ 7-day average") for x in a["dataUsed"]), a["dataUsed"]


def test_no_co2_factor_when_7_day_average_is_at_or_below_limit(c):
    _replace("co2", [(2.5, h) for h in range(0, 24 * 7)], "mmHg")  # exactly 2.5: not above
    draft = FatiguePatternRule().evaluate(RuleContext())
    assert draft is not None and CO2_FACTOR not in draft.possible_factors
    assert not any(x.startswith("Cabin CO₂") for x in draft.data_used)


def test_co2_uses_the_7_day_average_not_a_single_high_reading(c):
    # one 6 mmHg spike among 2.0 readings over 7 days: average stays below 2.5
    _replace("co2", [(6.0, 1)] + [(2.0, h) for h in range(2, 24 * 7)], "mmHg")
    assert CO2_FACTOR not in cabin_factors(RuleContext(), RuleContext().now - timedelta(hours=72))[0]


def test_temperature_outside_range_in_window_is_a_factor_with_its_reading_ids(c):
    ids = _replace("cabin_temp", [(22.0, 5), (26.0, 10), (22.5, 20)], "°C")  # 26 > 25 °C
    draft = FatiguePatternRule().evaluate(RuleContext())
    assert TEMP_FACTOR in draft.possible_factors
    assert ids[1] in draft.data_used and ids[0] not in draft.data_used
    slp = ShortSleepRule().evaluate(RuleContext())
    assert TEMP_FACTOR in slp.possible_factors and ids[1] in slp.data_used


def test_out_of_range_reading_before_the_window_is_ignored(c):
    _replace("humidity", [(45.0, 1), (70.0, 24 * 6)], "%")  # 70 % six days ago, outside the 3-night window
    draft = FatiguePatternRule().evaluate(RuleContext())
    assert HUMIDITY_FACTOR not in draft.possible_factors


def test_many_out_of_range_readings_are_capped_in_data_used(c):
    _replace("humidity", [(20.0, h) for h in range(1, 31)], "%")  # 30 readings below 30 %
    factors, used = cabin_factors(RuleContext(), RuleContext().now - timedelta(hours=48))
    assert HUMIDITY_FACTOR in factors
    hum = [u for u in used if "humidity" in u]
    assert len(hum) == MAX_IDS + 1 and hum[-1].startswith("…and 20 more humidity readings")


def test_threshold_without_a_real_source_adds_no_factor(c):
    _replace("cabin_temp", [(30.0, 2)], "°C")
    ctx = RuleContext()
    patched = dict(ctx.thresholds)
    patched["co2_headache_avg_max"] = Threshold(value=2.5, unit="mmHg", source="TODO", note="")
    patched["cabin_temp_max"] = Threshold(value=25, unit="°C", source="Team decision", note="")
    ctx.__dict__["thresholds"] = patched  # cached_property override
    factors, used = cabin_factors(ctx, ctx.now - timedelta(hours=72))
    assert factors == [] and used == []


def test_factor_wording_never_names_a_cause():
    for f in (CO2_FACTOR, TEMP_FACTOR, HUMIDITY_FACTOR):
        assert f.endswith("(possible link, not a confirmed cause)")
