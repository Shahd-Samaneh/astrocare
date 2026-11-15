"""Monitoring API (owners: Haya + Wala).

Working stubs that read the DB. Extend freely inside this folder.
"""
from __future__ import annotations

import re
import statistics
from datetime import timedelta
from typing import Literal, Optional, get_args

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from server.core import db
from server.core.config import has_real_source, iso, parse_ts, threshold, thresholds, utcnow
from server.core.models import (
    CABIN_METRICS, METRICS, Alert, AlertStatus, ApiModel, CabinMetric, CabinReading, Metric, Profile,
    NextStep, Quality, Reading, Resource, Sensor, Source,
)
from server.core.simulator import UNITS
from server.core.status import mission_clock, mission_day_start

from server.rules.resources import check_resource

from . import bone, cabin_guidance, vision
from .bone import router as bone_router
from .vision import router as vision_router

router = APIRouter(tags=["monitoring"])
router.include_router(vision_router)  # /vision/checks, /vision/summary
router.include_router(bone_router)  # /bone/estimate


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


class CabinLimit(ApiModel):
    """A sourced limit from config/thresholds.yaml, shown under the cabin value.

    min/max are the threshold values as written (None = no bound on that side);
    window_minutes is set when the limit applies to an average (co2).
    source is the full yaml text; source_label a short form for the screen.
    name labels the range when it has one ("Comfort zone" = [V2 6013]).
    health_* is the wider [V2 6012] crew-health limit (R-CAB-02 raises review outside it).
    """

    min: Optional[float] = None
    max: Optional[float] = None
    unit: str
    window_minutes: Optional[int] = None
    source: str
    source_label: str
    name: Optional[str] = None
    health_min: Optional[float] = None
    health_max: Optional[float] = None
    health_source_label: Optional[str] = None


class CabinGuidanceStep(NextStep):
    """One "What to do" step on a cabin tile (cabin_guidance.py), resource-checked like an alert step.

    source is the full citation for the step (cabin_guidance.SOURCES)."""

    source: str


class CabinLatest(ApiModel):
    """Latest cabin reading plus whether it sits inside the usual range.

    value/unit/ts describe the latest reading; status is the comparison result.
    For co2 the status is judged on the 1-hour average, not this single value.
    stale uses the vitals rule: no reading for longer than stale_minutes.
    limit is only present when thresholds.yaml has a numeric limit with a real source.
    guidance: "What to do" steps, only when the status is unusual for that metric (empty otherwise).
    alert_id: the open R-CAB-0x alert for this metric, when there is one.
    """

    metric: CabinMetric
    value: Optional[float] = None
    unit: str
    ts: Optional[str] = None
    status: CabinStatus
    age_minutes: Optional[int] = None
    stale: bool = False
    limit: Optional[CabinLimit] = None
    guidance: list[CabinGuidanceStep] = []
    alert_id: Optional[str] = None


# Which threshold keys form each metric's displayed limit. Noise has none: its yaml entry is a
# team-decision SD multiplier on a rolling baseline, not a sourced number.
_CABIN_LIMIT_KEYS: dict[str, tuple[Optional[str], Optional[str], Optional[str]]] = {
    # metric: (min key, max key, averaging-window key)
    "co2": (None, "co2_max", "co2_avg_window_minutes"),
    "cabin_temp": ("cabin_temp_min", "cabin_temp_max", None),
    "humidity": ("humidity_min", "humidity_max", None),
}
_CABIN_LIMIT_NAMES = {"cabin_temp": "Comfort zone", "humidity": "Comfort zone"}  # [V2 6013]
# [V2 6012] crew-health limits, shown next to the comfort zone (R-CAB-02 uses them for review).
_CABIN_HEALTH_KEYS = {
    "cabin_temp": ("cabin_temp_health_min", "cabin_temp_health_max"),
    "humidity": ("humidity_health_min", "humidity_health_max"),
}

def _source_label(source: str) -> str:
    """'NASA-STD-3001 Vol. 2 Rev D [V2 6013] …, via …' -> 'NASA-STD-3001 [V2 6013]'."""
    standard = source.split(" Vol.")[0].split(" [")[0].split(",")[0].strip()
    req = re.search(r"\[V\d+ \d+\]", source)
    return f"{standard} {req.group(0)}" if req else standard


def _sourced_pair(all_t: dict, lo_key: str, hi_key: str) -> bool:
    return all(k in all_t and all_t[k].value is not None and has_real_source(all_t[k]) for k in (lo_key, hi_key))


def _cabin_limit(metric: str) -> Optional[CabinLimit]:
    keys = _CABIN_LIMIT_KEYS.get(metric)
    if not keys:
        return None
    all_t = thresholds()
    lo_key, hi_key, window_key = keys
    bounds = [all_t.get(k) if k else None for k in (lo_key, hi_key)]
    if any(k and (all_t.get(k) is None or all_t[k].value is None or not has_real_source(all_t[k]))
           for k in (lo_key, hi_key)):
        return None  # a bound without a number or a real source: show no limit at all
    first = next(b for b in bounds if b is not None)
    window = all_t.get(window_key) if window_key else None
    health = _CABIN_HEALTH_KEYS.get(metric)
    health_t = (all_t[health[0]], all_t[health[1]]) if health and _sourced_pair(all_t, *health) else None
    return CabinLimit(
        name=_CABIN_LIMIT_NAMES.get(metric),
        health_min=float(health_t[0].value) if health_t else None,
        health_max=float(health_t[1].value) if health_t else None,
        health_source_label=_source_label(health_t[0].source) if health_t else None,
        min=float(bounds[0].value) if bounds[0] is not None else None,
        max=float(bounds[1].value) if bounds[1] is not None else None,
        unit=first.unit,
        window_minutes=int(window.value) if window is not None and window.value is not None else None,
        source=first.source,
        source_label=_source_label(first.source),
    )


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


def _cabin_guidance(metric: str, status: CabinStatus, now, profile: Optional[Profile],
                    resources: list[Resource]) -> tuple[list[CabinGuidanceStep], Optional[str]]:
    """Steps for an unusual cabin value (resource availability stamped) and the open alert, if any."""
    key = cabin_guidance.guidance_key(metric, status)
    if key is None:
        return [], None
    steps = [
        CabinGuidanceStep(**check_resource(g.to_next_step(), profile, resources, now).model_dump(),
                          source=cabin_guidance.SOURCES[g.source])
        for g in cabin_guidance.steps(key)
    ]
    rows = db.query("alerts", "rule_id = ? AND status != 'closed'", (cabin_guidance.RULE_FOR_KEY[key],),
                    order_by="ts DESC", limit=1)
    return steps, (rows[0]["id"] if rows else None)


@router.get("/cabin/latest")
def cabin_latest() -> list[CabinLatest]:
    """Latest reading per cabin metric with a 'usual'/'above_usual'/'below_usual' status.

    co2 is compared with co2_max on its 1-hour average; cabin_temp and humidity
    with their usual ranges; noise with its last-7-days mean ± 2 SD baseline.
    """
    now = utcnow()
    stale_min = float(threshold("stale_minutes"))
    profile_rows = db.query("profiles", limit=1)
    profile = Profile.model_validate(profile_rows[0]) if profile_rows else None
    resources = [Resource.model_validate(r) for r in db.query("resources")]
    out: list[CabinLatest] = []
    for metric in CABIN_METRICS:
        limit = _cabin_limit(metric)
        rows = db.query("cabin_readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        if not rows:
            out.append(CabinLatest(metric=metric, value=None, unit=UNITS[metric], ts=None, status="missing",
                                   limit=limit))
            continue
        latest = CabinReading.model_validate(rows[0])
        age = int((now - parse_ts(latest.ts)).total_seconds() // 60)
        status = _cabin_status(metric, latest, now)
        guidance, alert_id = _cabin_guidance(metric, status, now, profile, resources)
        out.append(CabinLatest(
            metric=metric, value=latest.value, unit=latest.unit, ts=latest.ts,
            status=status,
            age_minutes=age, stale=age > stale_min,  # same rule as GET /readings/latest
            limit=limit, guidance=guidance, alert_id=alert_id,
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
    "bone_muscle": ("R-EX-", "R-EXW-", "R-MSK-"),  # R-EX-01 missed exercise -> review
    "radiation": ("R-RAD-",),
    "vision": ("R-VIS-", "R-SANS-"),
    "thermoregulation": ("R-DATA-", "R-THERM-"),
}

BodySystemStatus = Literal["stable", "review", "no_data"]
_NO_MEASUREMENTS = "No connected measurements"


# The manual-reading endpoint (POST /readings/manual) takes any vital Metric, skin_temp included.
THERMO_MANUAL_ENTRY = "skin_temp" in get_args(Metric)


class ThermoDetail(ApiModel):
    """Extra lines for the thermoregulation tile.

    status_text: the word shown as the status ("Stable", "Review", "Sensor disconnected", "No data").
    fresh: the latest skin temperature is within stale_minutes; when False the value is dimmed.
    last_ts: time of the latest skin temperature reading (any quality), if any.
    manual_entry: POST /readings/manual accepts skin_temp.
    cabin: cabin temperature with its sourced comfort zone; cabin_source the full limit source.
    """

    status_text: str
    fresh: bool
    last_ts: Optional[str] = None
    manual_entry: bool = False
    cabin: Optional[str] = None
    cabin_source: Optional[str] = None


class BodySystem(ApiModel):
    """A Today-screen tile for one physiological system.

    status_label: short qualifier shown after the status ("within limit"); None for most tiles.
    simulated: the tile's value is a simulated estimate (radiation), not a measurement.
    reason: one line under the status saying why the system is tracked this way (bone & muscle).
    Vision has no sensor: its tile reflects the crew's self-check (server/features/monitoring/vision.py).
    """

    id: str
    status: BodySystemStatus
    text: str
    alert_id: Optional[str] = None
    status_label: Optional[str] = None
    simulated: bool = False
    reason: Optional[str] = None
    thermo: Optional[ThermoDetail] = None


# ---- Radiation estimate -----------------------------------------------------
# No dosimeter is connected. The dose is estimated as mission day × a NASA-measured deep-space
# rate (MSL RAD cruise). Both numbers come from thresholds.yaml with a real source; without them
# the estimate is unavailable (no fallback numbers).
RADIATION_LABEL = "Estimate · simulated · MSL RAD rate"
RADIATION_NOTE = "No dosimeter connected; this is an estimate from a NASA-measured deep-space rate."
RADIATION_SCOPE_NOTE = "This mission only: dose from earlier missions is not included."
ISS_NEUTRON_COMPARISON = "For comparison: on the ISS, neutrons are about 30% of the dose (CSA, CANS)"
ISS_NEUTRON_SOURCE = "Canadian Space Agency, Monitoring radiation for astronaut health, 2026 (references/csa-radiation-monitoring.txt)"
_RAD_LIMIT_KEY = "radiation_career_limit_msv"
_RAD_RATE_KEY = "radiation_deep_space_rate_msv_per_day"


class RadiationEstimate(ApiModel):
    """Cumulative dose estimate for GET /radiation/estimate (and the Today tile, and the report).

    cumulative_msv and pct_of_limit are rounded to whole numbers (the rate has two significant
    figures). within_limit compares with the sourced career limit ("shall be less than 600 mSv").
    """

    available: bool
    mission_day: int
    rate_msv_per_day: Optional[float] = None
    cumulative_msv: Optional[int] = None
    career_limit_msv: Optional[float] = None
    pct_of_limit: Optional[int] = None
    within_limit: Optional[bool] = None
    label: str = RADIATION_LABEL
    source: Source = "simulated"
    rate_source: Optional[str] = None
    rate_source_label: Optional[str] = None
    limit_source: Optional[str] = None
    limit_source_label: Optional[str] = None
    note: str = RADIATION_NOTE
    scope_note: str = RADIATION_SCOPE_NOTE
    comparison: str = ISS_NEUTRON_COMPARISON
    comparison_source: str = ISS_NEUTRON_SOURCE


def _half_up(x: float) -> int:
    return int(x + 0.5)  # x >= 0 here; avoids round()'s half-to-even


def radiation_estimate(mission_day: Optional[int] = None) -> RadiationEstimate:
    day = mission_clock()[1] if mission_day is None else mission_day
    all_t = thresholds()
    limit_t, rate_t = all_t.get(_RAD_LIMIT_KEY), all_t.get(_RAD_RATE_KEY)
    if any(t is None or t.value is None or not has_real_source(t) for t in (limit_t, rate_t)):
        return RadiationEstimate(available=False, mission_day=day)
    limit, rate = float(limit_t.value), float(rate_t.value)
    dose = max(day, 0) * rate
    return RadiationEstimate(
        available=True, mission_day=day, rate_msv_per_day=rate,
        cumulative_msv=_half_up(dose), career_limit_msv=limit, pct_of_limit=_half_up(dose / limit * 100),
        within_limit=dose < limit,
        rate_source=rate_t.source, rate_source_label=_source_label(rate_t.source),
        limit_source=limit_t.source, limit_source_label=_source_label(limit_t.source),
    )


def _radiation(day: int) -> tuple[BodySystemStatus, str, Optional[str]]:
    est = radiation_estimate(day)
    if not est.available:
        return "no_data", _NO_MEASUREMENTS, None
    text = f"{est.cumulative_msv} mSv · {est.pct_of_limit}% of career limit (estimate)"
    if est.within_limit:
        return "stable", text, "within limit"
    # The sourced limit itself, not an invented review fraction.
    return "review", text, "at or above career limit"


@router.get("/radiation/estimate")
def get_radiation_estimate() -> RadiationEstimate:
    return radiation_estimate()


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
    """Stable: exercise done or partial on most planned past days of this week (today excluded).
    Review: fewer than that, or R-EX-01 is open (missed on 2 days in a row; applied by the caller
    through SYSTEM_RULE_PREFIXES, so the tile and the alert always agree)."""
    c = bone.week_adherence(today)
    if c["done"] + c["partial"] + c["skipped"] == 0:
        return "no_data", "No exercise logged this week"
    text = f"{c['done']} done, {c['partial']} partial this week"
    return ("stable" if bone.most_days_exercised(c) else "review"), text


def _num(v: float) -> str:
    """22.50 -> '22.5', 20.0 -> '20' (one decimal at most, as the cabin tiles show it)."""
    return f"{round(v, 1):g}"


def _ago(minutes: float) -> str:
    """Same wording as the app's relativeTime(): 'just now', '5 min ago', '6 h ago', '2 days ago'."""
    m = int(minutes)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    if m < 1440:
        return f"{m // 60} h ago"
    d = m // 1440
    return f"{d} day{'' if d == 1 else 's'} ago"


def _thermo_cabin(now) -> tuple[Optional[str], Optional[str]]:
    """'Cabin 22.5 °C · comfort zone 20–25 °C (NASA-STD-3001 [V2 6013])' and the full limit source.

    Uses the same sourced limit as the cabin tiles (_cabin_limit); without a sourced limit only
    the reading is shown, and a stale cabin reading says so."""
    limit = _cabin_limit("cabin_temp")
    rows = db.query("cabin_readings", "metric = 'cabin_temp'", order_by="ts DESC", limit=1)
    if not rows and limit is None:
        return None, None
    parts: list[str] = []
    if rows:
        r = CabinReading.model_validate(rows[0])
        age = (now - parse_ts(r.ts)).total_seconds() / 60
        parts.append(f"Cabin {_num(r.value)} {r.unit}" + (f" (stale, {_ago(age)})" if age > float(threshold("stale_minutes")) else ""))
    else:
        parts.append("Cabin: no reading")
    if limit is not None and limit.min is not None and limit.max is not None:
        name = (limit.name or "range").lower()
        parts.append(f"{name} {_num(limit.min)}–{_num(limit.max)} {limit.unit} ({limit.source_label})")
    return " · ".join(parts), (limit.source if limit else None)


def _thermoregulation(profile: Optional[Profile], now, sensors: list[Sensor]) -> tuple[BodySystemStatus, str, ThermoDetail]:
    """Stable only with a fresh, good-quality skin temperature inside the personal baseline;
    review when fresh and good but outside it. Stale or missing data is never stable: it shows
    the last known value with its age and "Sensor disconnected" (sensor down) or "No data"."""
    rows = db.query("readings", "metric = 'skin_temp'", order_by="ts DESC", limit=1)
    sensor = next((s for s in sensors if "skin_temp" in s.metrics), None)
    r = Reading.model_validate(rows[0]) if rows else None
    age = (now - parse_ts(r.ts)).total_seconds() / 60 if r else None
    fresh = r is not None and age is not None and age <= float(threshold("stale_minutes"))
    cabin, cabin_source = _thermo_cabin(now)

    def detail(status_text: str) -> ThermoDetail:
        return ThermoDetail(status_text=status_text, fresh=fresh, last_ts=r.ts if r else None,
                            manual_entry=THERMO_MANUAL_ENTRY, cabin=cabin, cabin_source=cabin_source)

    if r is None or age is None or not fresh:
        down = sensor is not None and sensor.status == "disconnected"
        label = "Sensor disconnected" if down else "No data"
        text = f"Last: {_num(r.value)} {r.unit} · {_ago(age)}" if r is not None and age is not None else "No skin temperature reading"
        return "no_data", text, detail(label)
    value = f"Skin temp {_num(r.value)} {r.unit}"
    if r.quality != "good":
        return "no_data", f"{value} · {r.quality} quality · {_ago(age)}", detail("No data")
    base = profile.baseline.get("skin_temp") if profile else None
    if base is None:
        return "no_data", f"{value} · no personal baseline", detail("No data")
    if _outside_baseline(r.value, base.mean, base.sd):
        return "review", f"{value} · outside baseline", detail("Review")
    return "stable", f"{value} · in baseline", detail("Stable")


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
    }
    th_status, th_text, th_detail = _thermoregulation(profile, now, sensors)
    computed["thermoregulation"] = (th_status, th_text)
    rad_status, rad_text, rad_label = _radiation(today)
    computed["radiation"] = (rad_status, rad_text)
    vis_status, vis_text, vis_label = vision.body_system_tile(now)
    computed["vision"] = (vis_status, vis_text)

    out: list[BodySystem] = []
    for system in BODY_SYSTEMS:
        status, text = computed[system]
        extra: dict = {}
        if system == "radiation":
            extra = {"status_label": rad_label, "simulated": rad_status != "no_data"}
        elif system == "vision":
            extra = {"status_label": vis_label}
        elif system == "bone_muscle":
            extra = {"reason": bone.WHY}
        elif system == "thermoregulation":
            extra = {"thermo": th_detail}
        alert_id = None
        alert = next((a for a in open_alerts if a.rule_id.startswith(SYSTEM_RULE_PREFIXES[system])), None)
        if alert is not None:
            if alert.rule_id.startswith("R-DATA-"):
                alert_id = alert.id  # R-DATA-* explains no_data; it never forces review
            else:
                status, alert_id = "review", alert.id
                extra.pop("status_label", None)  # "within limit" would contradict the alert
                if "thermo" in extra:
                    extra["thermo"] = extra["thermo"].model_copy(update={"status_text": "Review"})
        out.append(BodySystem(id=system, status=status, text=text, alert_id=alert_id, **extra))
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