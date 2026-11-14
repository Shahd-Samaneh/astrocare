"""Monitoring API (owners: Haya + Wala).

Working stubs that read the DB. Extend freely inside this folder.
"""
from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, parse_ts, threshold, utcnow
from server.core.models import (
    CABIN_METRICS, METRICS, Alert, AlertStatus, ApiModel, CabinMetric, CabinReading, Metric, Profile,
    Quality, Reading, Resource, Sensor,
)
from server.core.simulator import UNITS
from server.core.status import mission_clock, mission_day_start

router = APIRouter(tags=["monitoring"])


@router.get("/profile")
def get_profile() -> Profile:
    rows = db.query("profiles", limit=1)
    if not rows:
        raise HTTPException(404, "No profile")
    return Profile.model_validate(rows[0])


@router.get("/readings")
def list_readings(
    metric: Optional[Metric] = None,
    hours: float = Query(24, gt=0, description="Look-back window in hours"),
    limit: int = Query(2000, gt=0, le=20000),
) -> list[Reading]:
    where, params = "ts >= ?", [iso(utcnow() - timedelta(hours=hours))]
    if metric:
        where += " AND metric = ?"
        params.append(metric)
    rows = db.query("readings", where, tuple(params), order_by="ts", limit=limit)
    return [Reading.model_validate(r) for r in rows]


class LatestReading(ApiModel):
    """Latest value per metric with an effective quality (stale/missing computed now)."""

    metric: Metric
    reading: Optional[Reading] = None
    quality: Quality
    age_minutes: Optional[int] = None
    sensor_name: Optional[str] = None
    sensor_status: Optional[str] = None


@router.get("/readings/latest")
def latest_readings() -> list[LatestReading]:
    now = utcnow()
    stale_min = float(threshold("stale_minutes"))
    day_start = mission_day_start(now)
    sensors = [Sensor.model_validate(s) for s in db.query("sensors")]
    out = []
    for metric in METRICS:
        rows = db.query("readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        sensor = next((s for s in sensors if metric in s.metrics), None)
        r = Reading.model_validate(rows[0]) if rows else None
        age = int((now - parse_ts(r.ts)).total_seconds() // 60) if r else None
        if r is None or (metric.startswith("bp_") and parse_ts(r.ts) < day_start):
            quality = "missing"  # spot-check metrics: missing when nothing since the mission day began
        elif age is not None and age > stale_min and not metric.startswith("bp_"):
            quality = "stale"
        else:
            quality = r.quality
        out.append(LatestReading(
            metric=metric, reading=r, quality=quality, age_minutes=age,
            sensor_name=sensor.name if sensor else None, sensor_status=sensor.status if sensor else None,
        ))
    return out


class ManualReadingIn(ApiModel):
    metric: Metric
    value: float
    unit: Optional[str] = None
    ts: Optional[str] = None


@router.post("/readings/manual", status_code=201)
def add_manual_reading(body: ManualReadingIn) -> Reading:
    profile = db.query("profiles", limit=1)
    reading = Reading(
        id=db.new_id("r-manual"), astronaut_id=profile[0]["id"] if profile else "c2", metric=body.metric,
        value=body.value, unit=body.unit or UNITS[body.metric], ts=body.ts or iso(utcnow()),
        source="manual", quality="good",
    )
    db.insert("readings", reading.model_dump())
    db.log_action("crew", "manual_reading", reading.id)
    return reading


@router.get("/cabin")
def list_cabin(metric: Optional[CabinMetric] = None, hours: float = Query(24, gt=0)) -> list[CabinReading]:
    where, params = "ts >= ?", [iso(utcnow() - timedelta(hours=hours))]
    if metric:
        where += " AND metric = ?"
        params.append(metric)
    return [CabinReading.model_validate(r) for r in db.query("cabin_readings", where, tuple(params), order_by="ts")]


# ---- Cabin "Today" status -------------------------------------------------
# Status vocabulary for a cabin metric compared with its usual range/baseline.
# "missing" means we have no reading at all for that metric.
CabinStatus = Literal["usual", "above_usual", "below_usual", "missing"]


class CabinLatest(ApiModel):
    """Latest cabin reading plus whether it sits inside the usual range.

    value/unit/ts describe the latest reading; status is the comparison result.
    For co2 the status is judged on the 1-hour average, not this single value.
    """

    metric: CabinMetric
    value: Optional[float] = None
    unit: str
    ts: Optional[str] = None
    status: CabinStatus


def _range_status(value: float, low: float, high: float) -> CabinStatus:
    if value > high:
        return "above_usual"
    if value < low:
        return "below_usual"
    return "usual"


def _cabin_status(metric: str, latest: CabinReading, now) -> CabinStatus:
    """Compare the latest cabin reading with its configured usual range/baseline."""
    if metric == "co2":
        co2_max = threshold("co2_max")
        if co2_max is None:
            return "usual"  # no sourced limit yet; cannot judge
        window = float(threshold("co2_avg_window_minutes"))
        since = iso(now - timedelta(minutes=window))
        rows = db.query("cabin_readings", "metric = ? AND ts >= ?", ("co2", since))
        values = [r["value"] for r in rows] or [latest.value]
        return "above_usual" if statistics.fmean(values) > co2_max else "usual"

    if metric == "cabin_temp":
        return _range_status(latest.value, threshold("cabin_temp_min"), threshold("cabin_temp_max"))

    if metric == "humidity":
        return _range_status(latest.value, threshold("humidity_min"), threshold("humidity_max"))

    if metric == "noise":
        days = float(threshold("noise_baseline_days"))
        k = float(threshold("noise_sd_multiplier"))
        since = iso(now - timedelta(days=days))
        rows = db.query("cabin_readings", "metric = ? AND ts >= ?", ("noise", since))
        values = [r["value"] for r in rows]
        if len(values) < 2:
            return "usual"  # not enough history for a baseline
        mean, sd = statistics.fmean(values), statistics.stdev(values)
        if sd == 0:
            return "usual"
        return _range_status(latest.value, mean - k * sd, mean + k * sd)

    return "usual"


@router.get("/cabin/latest")
def cabin_latest() -> list[CabinLatest]:
    """Latest reading per cabin metric with a 'usual'/'above_usual'/'below_usual' status.

    co2 is compared with co2_max on its 1-hour average; cabin_temp and humidity
    with their usual ranges; noise with its last-7-days mean ± 2 SD baseline.
    """
    now = utcnow()
    out: list[CabinLatest] = []
    for metric in CABIN_METRICS:
        rows = db.query("cabin_readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        if not rows:
            out.append(CabinLatest(metric=metric, value=None, unit=UNITS[metric], ts=None, status="missing"))
            continue
        latest = CabinReading.model_validate(rows[0])
        out.append(CabinLatest(
            metric=metric, value=latest.value, unit=latest.unit, ts=latest.ts,
            status=_cabin_status(metric, latest, now),
        ))
    return out


# ---- Body-systems tiles (Today screen) ------------------------------------
# One tile per physiological system. Status is derived from existing readings,
# baselines and thresholds only (no new clinical numbers), and may be forced to
# "review" by an open alert that belongs to the system.
BODY_SYSTEMS = (
    "cardiovascular", "respiratory", "sleep", "cognition",
    "bone_muscle", "radiation", "vision", "thermoregulation",
)

# Rule-id prefixes that belong to each system, for linking open alerts. Most are
# reserved for rules that do not exist yet; today only R-DATA-01 is produced.
SYSTEM_RULE_PREFIXES: dict[str, tuple[str, ...]] = {
    "cardiovascular": ("R-HR-",),
    "respiratory": ("R-SPO2-", "R-RESP-"),
    "sleep": ("R-FAT-", "R-SLEEP-"),
    "cognition": ("R-FAT-", "R-COG-"),
    "bone_muscle": ("R-EXW-", "R-MSK-"),
    "radiation": ("R-RAD-",),
    "vision": ("R-VIS-", "R-SANS-"),
    "thermoregulation": ("R-DATA-", "R-THERM-"),
}

BodySystemStatus = Literal["stable", "review", "no_data"]
_NO_MEASUREMENTS = "No connected measurements"


class BodySystem(ApiModel):
    """A Today-screen tile for one physiological system."""

    id: str
    status: BodySystemStatus
    text: str
    alert_id: Optional[str] = None


def _profile() -> Optional[Profile]:
    rows = db.query("profiles", limit=1)
    return Profile.model_validate(rows[0]) if rows else None


def _latest_good(metric: str) -> Optional[Reading]:
    rows = db.query("readings", "metric = ? AND quality = 'good'", (metric,), order_by="ts DESC", limit=1)
    return Reading.model_validate(rows[0]) if rows else None


def _outside_baseline(value: float, mean: float, sd: float) -> bool:
    k = float(threshold("hr_sd_multiplier"))
    return value < mean - k * sd or value > mean + k * sd


def _cardiovascular(profile: Optional[Profile]) -> tuple[BodySystemStatus, str]:
    r = _latest_good("heart_rate")
    base = profile.baseline.get("heart_rate") if profile else None
    if r is None or base is None:
        return "no_data", _NO_MEASUREMENTS
    k = float(threshold("hr_sd_multiplier"))
    if r.value > base.mean + k * base.sd:
        return "review", "HR above baseline"
    if r.value < base.mean - k * base.sd:
        return "review", "HR below baseline"
    return "stable", "HR in baseline"


def _respiratory() -> tuple[BodySystemStatus, str]:
    r = _latest_good("spo2")
    if r is None:
        return "no_data", _NO_MEASUREMENTS
    v = round(r.value)
    if r.value < float(threshold("spo2_min")):
        return "review", f"SpO₂ {v}% (low)"
    return "stable", f"SpO₂ {v}%"


def _sleep() -> tuple[BodySystemStatus, str]:
    rows = db.query("sleep_sessions", order_by="start DESC", limit=3)
    if not rows:
        return "no_data", _NO_MEASUREMENTS
    short_h = float(threshold("sleep_short_hours"))
    n = sum(1 for r in rows if r["duration_min"] / 60 < short_h)
    if n >= 2:
        return "review", f"{n} short nights"
    if n == 1:
        return "stable", "1 short night"
    return "stable", "Sleep in range"


def _cognition(profile: Optional[Profile]) -> tuple[BodySystemStatus, str]:
    rows = db.query("cognitive_tests", order_by="ts DESC", limit=1)
    base = profile.baseline.get("pvt_median_ms") if profile else None
    if not rows or base is None or base.mean == 0:
        return "no_data", _NO_MEASUREMENTS
    pct = (rows[0]["median_ms"] - base.mean) / base.mean * 100
    rounded = round(pct)
    if pct > float(threshold("attention_slower_pct")):
        return "review", f"reaction +{rounded} %"
    sign = "+" if rounded > 0 else ""
    return "stable", f"reaction {sign}{rounded} %"


def _bone_muscle(today: int) -> tuple[BodySystemStatus, str]:
    # Only past days of this mission week (today excluded: it is not over yet).
    plan_day = {p["id"]: p["day"] for p in db.query("exercise_plans")}
    logs = [l for l in db.query("exercise_logs") if today - 6 <= plan_day.get(l["plan_id"], -1) <= today - 1]
    if not logs:
        return "no_data", "No exercise logged this week"
    done = sum(1 for l in logs if l["status"] == "done")
    partial = sum(1 for l in logs if l["status"] == "partial")
    return "stable", f"{done} done, {partial} partial this week"


def _thermoregulation(profile: Optional[Profile], now, sensors: list[Sensor]) -> tuple[BodySystemStatus, str]:
    rows = db.query("readings", "metric = 'skin_temp'", order_by="ts DESC", limit=1)
    sensor = next((s for s in sensors if "skin_temp" in s.metrics), None)
    r = Reading.model_validate(rows[0]) if rows else None
    age = (now - parse_ts(r.ts)).total_seconds() / 60 if r else None
    if r is None or (age is not None and age > float(threshold("stale_minutes"))):
        if sensor and sensor.status != "connected":
            return "no_data", f"{sensor.name.split()[-1].lower()} {sensor.status.replace('_', ' ')}"
        return "no_data", _NO_MEASUREMENTS
    base = profile.baseline.get("skin_temp") if profile else None
    if base is None:
        return "no_data", _NO_MEASUREMENTS
    if _outside_baseline(r.value, base.mean, base.sd):
        return "review", "Skin temp out of baseline"
    return "stable", "Skin temp in baseline"


@router.get("/body-systems")
def body_systems() -> list[BodySystem]:
    now = utcnow()
    today = mission_clock()[1]
    profile = _profile()
    sensors = [Sensor.model_validate(s) for s in db.query("sensors")]
    open_alerts = [Alert.model_validate(a) for a in db.query("alerts", "status != 'closed'", order_by="ts DESC")]

    computed: dict[str, tuple[BodySystemStatus, str]] = {
        "cardiovascular": _cardiovascular(profile),
        "respiratory": _respiratory(),
        "sleep": _sleep(),
        "cognition": _cognition(profile),
        "bone_muscle": _bone_muscle(today),
        "radiation": ("no_data", _NO_MEASUREMENTS),
        "vision": ("no_data", _NO_MEASUREMENTS),
        "thermoregulation": _thermoregulation(profile, now, sensors),
    }

    out: list[BodySystem] = []
    for system in BODY_SYSTEMS:
        status, text = computed[system]
        alert_id = None
        alert = next((a for a in open_alerts if a.rule_id.startswith(SYSTEM_RULE_PREFIXES[system])), None)
        if alert is not None:
            if alert.rule_id.startswith("R-DATA-"):
                alert_id = alert.id  # R-DATA-* explains no_data; it never forces review
            else:
                status, alert_id = "review", alert.id
        out.append(BodySystem(id=system, status=status, text=text, alert_id=alert_id))
    return out


@router.get("/sensors")
def list_sensors() -> list[Sensor]:
    return [Sensor.model_validate(r) for r in db.query("sensors")]


@router.get("/alerts")
def list_alerts(status: Optional[AlertStatus] = None) -> list[Alert]:
    rows = db.query("alerts", "status = ?", (status,), order_by="ts DESC") if status else db.query("alerts", order_by="ts DESC")
    return [Alert.model_validate(r) for r in rows]


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> Alert:
    row = db.get("alerts", alert_id)
    if not row:
        raise HTTPException(404, "Alert not found")
    return Alert.model_validate(row)


class AckIn(ApiModel):
    actor: str = Field(default="crew")


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, body: Optional[AckIn] = None) -> Alert:
    if not db.get("alerts", alert_id):
        raise HTTPException(404, "Alert not found")
    db.update("alerts", alert_id, {"status": "ack"})
    db.log_action((body or AckIn()).actor, "ack_alert", alert_id)
    return get_alert(alert_id)


@router.get("/resources")
def list_resources(kind: Optional[str] = Query(None, pattern="^(medicine|equipment)$")) -> list[Resource]:
    rows = db.query("resources", "kind = ?", (kind,), order_by="name") if kind else db.query("resources", order_by="kind, name")
    return [Resource.model_validate(r) for r in rows]