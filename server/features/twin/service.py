"""Digital twin aggregator (owner: Shahd). Read-only: it never writes to the DB.

Every value comes from another feature's existing service function or the stored data:
  * monitoring: body_systems(), latest_readings(), cabin_latest(), list_sensors(),
    radiation_estimate(), vision.vision_summary(), bone.week_adherence()/bone_estimate()
  * daily: sleep.sleep_summary()
  * alerts: the open alerts in the `alerts` table (the same rows GET /alerts returns)
  * history: existing rules replayed on a BoundedContext (history.py)

Status vocabulary: ok | watch | review | urgent | nodata. A missing source gives "nodata" with
"No data", never an invented value. Check-in notes (`note_private`) are never read here.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from server.core import db
from server.core.config import REFERENCES_DIR, iso, parse_ts, threshold, utcnow
from server.core.models import CABIN_METRICS, Alert, Profile, Sensor
from server.core.status import mission_clock
from server.features.daily.exercise import load_plan_items
from server.features.daily.sleep import sleep_summary
from server.features.daily.sources import SOURCES as DAILY_SOURCES
from server.features.monitoring import bone, vision
from server.features.monitoring.router import (
    BodySystem, LatestReading, body_systems, cabin_latest, latest_readings, list_sensors, radiation_estimate,
)

from . import history
from .models import (
    ESTIMATE_LABEL, NO_DATA, REGION_IDS, TwinAlertRef, TwinDay, TwinRegion, TwinSensor, TwinSource,
    TwinState, TwinStatus, TwinTimeline, TwinValue,
)

# ---- region metadata ---------------------------------------------------------------
# id: (label, route, route label, NASA/reference source ids)
REGION_META: dict[str, tuple[str, str, str, list[str]]] = {
    "brain": ("Brain · sleep and attention", "/daily", "Daily log",
              ["nasa-hrp-sleep-risk", "nasa-hrp-bmed-risk", "nasa-pvt-iss"]),
    "eyes": ("Eyes · vision self-check", "/vision", "Vision check", ["nasa-hrp-risks"]),
    "heart": ("Heart", "/vitals", "Vitals", []),
    "lungs": ("Lungs · breathing and cabin air", "/vitals", "Vitals", []),
    "bones": ("Bones and muscle", "/bone", "Bone & muscle", ["nasa-hrp-risks", "nasa-bone-risk"]),
    "radiation": ("Radiation dose", "/radiation", "Radiation", ["nasa-msl-rad-cruise", "nasa-ochmo-radiation"]),
    "temperature": ("Skin temperature", "/vitals", "Vitals", []),
    "sensors": ("Body sensors", "/vitals", "Vitals", []),
}

# Which open alerts belong to which region (rule-id prefixes), for the card's alert links.
REGION_RULES: dict[str, tuple[str, ...]] = {
    "brain": ("R-FAT-", "R-SLP-", "R-CIRC-", "R-COG-"),
    "eyes": ("R-VIS-", "R-SANS-"),
    "heart": ("R-HR-",),
    "lungs": ("R-SPO2-", "R-RESP-", "R-CAB-01"),
    "bones": ("R-EX-", "R-MSK-"),
    "radiation": ("R-RAD-",),
    "temperature": ("R-THERM-", "R-DATA-"),
    "sensors": ("R-DATA-",),
}

# How an open alert moves the region status. None = linked on the card, status unchanged
# (R-DATA-01 explains missing data, it is not a health signal; same rule as the Today tiles).
# Rules not listed use their level: urgent -> urgent, review -> review, info -> watch.
RULE_STATUS: dict[str, Optional[TwinStatus]] = {
    "R-FAT-01": "review",  # spec: brain is "review" while R-FAT-01 is open
    "R-SLP-01": "watch",  # spec: brain is "watch" while R-SLP-01 is open
    "R-CIRC-01": "watch",
    "R-HR-01": "review",
    "R-CAB-01": "review",
    "R-EX-01": "review",  # same as the Bone & muscle tile
    "R-VIS-01": "review",  # same as the Vision tile
    "R-DATA-01": None,
}
_RANK: dict[str, int] = {"nodata": 0, "ok": 1, "watch": 2, "review": 3, "urgent": 4}

_TILE_STATUS: dict[str, TwinStatus] = {"stable": "ok", "review": "review", "no_data": "nodata"}
_ON_BODY = {"torso": "chest", "upper arm": "upperArm", "left wrist": "leftWrist"}


def worst(*statuses: Optional[str]) -> TwinStatus:
    present = [s for s in statuses if s]
    return max(present, key=lambda s: _RANK[s]) if present else "nodata"  # type: ignore[return-value]


def alert_status(a: Alert) -> Optional[TwinStatus]:
    if a.rule_id in RULE_STATUS:
        if a.rule_id == "R-SPO2-01":
            return "urgent" if a.level == "urgent" else "watch"
        return RULE_STATUS[a.rule_id]
    if a.rule_id.startswith("R-SPO2-"):
        return "urgent" if a.level == "urgent" else "watch"
    return {"urgent": "urgent", "review": "review"}.get(a.level, "watch")  # type: ignore[return-value]


# ---- small helpers -------------------------------------------------------------------
def num(v: float, digits: int = 1) -> float:
    r = round(float(v), digits)
    return int(r) if r == int(r) else r


def ago(minutes: Optional[float]) -> str:
    if minutes is None:
        return ""
    m = int(minutes)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    if m < 1440:
        return f"{m // 60} h ago"
    d = m // 1440
    return f"{d} day{'' if d == 1 else 's'} ago"


def _reference_title(ref_id: str) -> Optional[str]:
    for s in DAILY_SOURCES:
        if s.id == ref_id:
            return s.title
    path: Path = REFERENCES_DIR / f"{ref_id}.txt"
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    return first.removeprefix("title:").strip() or None


def source_titles(ids: Iterable[str]) -> tuple[list[str], list[TwinSource]]:
    """Only ids that resolve to a known reference; text sources ("Team decision", yaml keys) are dropped."""
    out_ids, titles = [], []
    for i in dict.fromkeys(ids):
        title = _reference_title(i)
        if title:
            out_ids.append(i)
            titles.append(TwinSource(id=i, title=title))
    return out_ids, titles


def _profile() -> Optional[Profile]:
    rows = db.query("profiles", limit=1)
    return Profile.model_validate(rows[0]) if rows else None


def _region(rid: str, status: TwinStatus, headline: str, values: list[TwinValue],
            alerts: list[Alert] = (), extra_sources: Iterable[str] = (), **extra) -> TwinRegion:
    label, route, route_label, base_sources = REGION_META[rid]
    ids, titles = source_titles([*base_sources, *extra_sources, *(s for a in alerts for s in a.sources)])
    return TwinRegion(
        id=rid, label=label, status=status, headline=headline, values=values,
        alerts=list(dict.fromkeys(a.rule_id for a in alerts)),
        alert_refs=[TwinAlertRef(id=a.id, rule_id=a.rule_id, title=a.title, level=a.level) for a in alerts],
        route=route, route_label=route_label, sources=ids, source_titles=titles, **extra,
    )


def _apply_alerts(status: TwinStatus, alerts: list[Alert]) -> TwinStatus:
    return worst(status, *(alert_status(a) for a in alerts)) if alerts else status


def body_sensors(sensors: list[Sensor]) -> list[TwinSensor]:
    """The crew member's sensors (cabin monitors excluded), with a 3D anchor when worn on the body."""
    out = []
    for s in sensors:
        if s.metrics and all(m in CABIN_METRICS for m in s.metrics):
            continue  # the habitat environment monitor is not a body sensor
        out.append(TwinSensor(id=s.id, name=s.name, location=s.location, status=s.status,
                              last_seen=s.last_seen, anchor=_ON_BODY.get(s.location.strip().lower())))
    return out


def _status_word(status: str) -> str:
    return status.replace("_", " ")


# ---- live state ------------------------------------------------------------------------
def _live_brain(tiles: dict[str, BodySystem], alerts: list[Alert]) -> TwinRegion:
    sleep_t, cog_t = tiles["sleep"], tiles["cognition"]
    summary = sleep_summary(3)
    nights = summary["nights"]
    last = summary["lastNight"]
    values = [
        TwinValue(label="Last night", value=last["hours"] if last else None, unit="h" if last else None),
        TwinValue(label="Short nights (last 3)",
                  value=f"{sum(1 for n in nights if n['short'])} of {len(nights)}" if nights else None),
        TwinValue(label="Attention test vs baseline", value=cog_t.text if cog_t.status != "no_data" else None),
        TwinValue(label="Fatigue pattern",
                  value="Possible · review" if any(a.rule_id == "R-FAT-01" for a in alerts) else "Not flagged"),
    ]
    if sleep_t.status == "no_data" and cog_t.status == "no_data":
        status: TwinStatus = "nodata"
    else:
        # A tile in review without the alert (e.g. reaction slower but sleep fine) is a "watch".
        status = "watch" if "review" in (sleep_t.status, cog_t.status) else "ok"
    status = _apply_alerts(status, alerts)
    headline = _brain_headline(status, sleep_t.text if sleep_t.status != "no_data" else None,
                               cog_t.text if cog_t.status != "no_data" else None,
                               any(a.rule_id == "R-SLP-01" for a in alerts))
    return _region("brain", status, headline, values, alerts)


def _brain_headline(status: str, sleep_text: Optional[str], cog_text: Optional[str], short_sleep: bool) -> str:
    if status == "nodata":
        return NO_DATA
    parts = [p for p in (sleep_text, cog_text) if p]
    lead = {"review": "Possible fatigue pattern · review",
            "watch": "Short sleep on recent nights · watch" if short_sleep else "Watch"}.get(status)
    return " · ".join([lead, *parts] if lead else parts) or NO_DATA


def _live_eyes(now: datetime, alerts: list[Alert]) -> TwinRegion:
    s = vision.vision_summary(now)
    if s.last_mission_day is None:
        return _region("eyes", _apply_alerts("nodata", alerts), "No self-check yet",
                       [TwinValue(label="Last self-check")], alerts)
    status: TwinStatus = "review" if s.status == "review" else ("watch" if s.due else "ok")
    values = [
        TwinValue(label="Last self-check", value=f"Mission day {s.last_mission_day}", quality="self-check"),
        TwinValue(label="Result vs baseline", value=s.result),
        TwinValue(label="Baseline", value=f"Mission day {s.baseline_mission_day}"),
    ]
    headline = {"review": "Possible change reported · review", "watch": "Self-check due"}.get(
        status, f"No change vs baseline (day {s.last_mission_day})")
    return _region("eyes", _apply_alerts(status, alerts), headline, values, alerts)


def _fresh(lr: Optional[LatestReading]) -> bool:
    return lr is not None and lr.reading is not None and lr.quality in ("good", "low")


def _reading_value(label: str, lr: Optional[LatestReading], digits: int = 0) -> TwinValue:
    if lr is None or lr.reading is None:
        return TwinValue(label=label, quality="missing")
    return TwinValue(label=label, value=num(lr.reading.value, digits), unit=lr.reading.unit, quality=lr.quality)


def _live_heart(tile: BodySystem, hr: Optional[LatestReading], alerts: list[Alert]) -> TwinRegion:
    values = [
        _reading_value("Heart rate", hr),
        # No ECG or rhythm sensor exists in the app: say so, never infer a rhythm.
        TwinValue(label="Rhythm", value=None, quality="missing"),
    ]
    if not _fresh(hr):
        last = f" · last {num(hr.reading.value, 0)} bpm {ago(hr.age_minutes)}" if hr and hr.reading else ""
        return _region("heart", _apply_alerts("nodata", alerts), f"No recent data{last}", values, alerts)
    bpm = num(hr.reading.value, 0)
    status: TwinStatus = _TILE_STATUS[tile.status] if tile.status != "no_data" else "ok"
    if hr.quality == "low":
        status = worst(status, "watch")
    status = _apply_alerts(status, alerts)
    headline = f"{bpm} bpm · {tile.text}" if tile.status != "no_data" else f"{bpm} bpm"
    return _region("heart", status, headline, values, alerts, pulse_bpm=float(bpm))


def _live_lungs(tile: BodySystem, spo2: Optional[LatestReading], resp: Optional[LatestReading],
                co2, alerts: list[Alert]) -> TwinRegion:
    co2_value = TwinValue(label="Cabin CO₂", quality="missing")
    if co2 is not None and co2.value is not None:
        co2_value = TwinValue(label="Cabin CO₂", value=num(co2.value), unit=co2.unit,
                              quality="stale" if co2.stale else "good")
    values = [_reading_value("SpO₂", spo2), _reading_value("Breathing rate", resp), co2_value]
    if not _fresh(spo2) and not _fresh(resp):
        return _region("lungs", _apply_alerts("nodata", alerts), "No recent data", values, alerts)
    status: TwinStatus = _TILE_STATUS.get(tile.status, "ok") if _fresh(spo2) else "ok"
    if co2 is not None and co2.status == "above_usual":
        status = worst(status, "review")
    if any(v.quality == "low" for v in values):
        status = worst(status, "watch")
    status = _apply_alerts(status, alerts)
    parts = []
    if _fresh(spo2):
        parts.append(f"SpO₂ {num(spo2.reading.value, 0)} %")
    if _fresh(resp):
        parts.append(f"{num(resp.reading.value, 0)} br/min")
    if co2 is not None and co2.value is not None:
        parts.append(f"CO₂ {num(co2.value)} {co2.unit}" + (" (above limit)" if co2.status == "above_usual" else ""))
    return _region("lungs", status, " · ".join(parts), values, alerts)


def _bone_estimate_value(day: int) -> TwinValue:
    est = bone.bone_estimate(day)
    if not est.available:
        return TwinValue(label="Bone density change (illustrative)")
    return TwinValue(label="Bone density change (illustrative)",
                     value=f"{est.estimated_loss_pct_min:g}–{est.estimated_loss_pct_max:g} % loss",
                     quality="illustrative")


def _live_bones(tile: BodySystem, today: int, alerts: list[Alert]) -> TwinRegion:
    c = bone.week_adherence(today)
    values = [
        TwinValue(label="Exercise this week",
                  value=None if tile.status == "no_data" else f"{c['done']} done, {c['partial']} partial of {c['planned']} planned"),
        _bone_estimate_value(today),
    ]
    status = _apply_alerts(_TILE_STATUS[tile.status], alerts)
    headline = NO_DATA + " · no exercise logged this week" if tile.status == "no_data" else tile.text
    return _region("bones", status, headline, values, alerts)


def radiation_region(day: int, alerts: list[Alert] = ()) -> TwinRegion:
    """Radiation is an estimate (mission day × MSL RAD 1.8 mSv/day), never a measurement."""
    est = radiation_estimate(day)
    if not est.available:
        return _region("radiation", _apply_alerts("nodata", list(alerts)), NO_DATA,
                       [TwinValue(label="Cumulative dose", quality="estimate")], list(alerts), estimate=True)
    values = [
        TwinValue(label="Cumulative dose", value=est.cumulative_msv, unit="mSv", quality="estimate"),
        TwinValue(label="Of career limit", value=est.pct_of_limit, unit="%", quality="estimate"),
        TwinValue(label="Career limit", value=num(est.career_limit_msv), unit="mSv"),
        TwinValue(label="Rate used", value=est.rate_msv_per_day, unit="mSv/day", quality="estimate"),
    ]
    status: TwinStatus = "ok" if est.within_limit else "review"
    headline = f"{est.cumulative_msv} mSv · {est.pct_of_limit}% of limit · {ESTIMATE_LABEL}"
    return _region("radiation", _apply_alerts(status, list(alerts)), headline, values, list(alerts), estimate=True)


def _live_temperature(tile: BodySystem, skin: Optional[LatestReading], sensors: list[TwinSensor],
                      alerts: list[Alert]) -> TwinRegion:
    patch = next((s for s in sensors if s.anchor == "upperArm"), None)
    thermo = tile.thermo
    values = [
        _reading_value("Skin temperature", skin, 1),
        TwinValue(label="Last reading", value=ago(skin.age_minutes) if skin and skin.reading else None),
        TwinValue(label="Patch", value=_status_word(patch.status) if patch else None),
    ]
    if thermo and thermo.cabin:
        values.append(TwinValue(label="Cabin", value=thermo.cabin))
    status = _apply_alerts(_TILE_STATUS[tile.status], alerts)
    word = thermo.status_text if thermo else ("No data" if tile.status == "no_data" else tile.status)
    return _region("temperature", status, f"{word} · {tile.text}", values, alerts)


def sensors_region(sensors: list[TwinSensor], alerts: list[Alert] = ()) -> TwinRegion:
    if not sensors:
        return _region("sensors", "nodata", NO_DATA, [], list(alerts), sensors=[])
    values = [TwinValue(label=s.name, value=_status_word(s.status), unit=None,
                        quality="good" if s.status == "connected" else "missing") for s in sensors]
    down = [s for s in sensors if s.status == "disconnected"]
    low = [s for s in sensors if s.status == "low_battery"]
    status: TwinStatus = "watch" if down or low else "ok"
    parts = []
    if down:
        parts.append(f"{len(down)} disconnected")
    if low:
        parts.append(f"{len(low)} low battery")
    headline = " · ".join(parts) if parts else f"All {len(sensors)} connected"
    return _region("sensors", status, headline, values, list(alerts), sensors=sensors)


def _open_alerts() -> list[Alert]:
    return [Alert.model_validate(a) for a in db.query("alerts", "status != 'closed'", order_by="ts DESC")]


def _alerts_for(region: str, alerts: list[Alert]) -> list[Alert]:
    return [a for a in alerts if a.rule_id.startswith(REGION_RULES[region])]


def _simulated() -> bool:
    return db.count("readings", "source = 'simulated'") > 0


def live_regions(now: Optional[datetime] = None) -> list[TwinRegion]:
    now = now or utcnow()
    today = mission_clock(now)[1]
    tiles = {t.id: t for t in body_systems()}
    latest = {lr.metric: lr for lr in latest_readings()}
    co2 = next((c for c in cabin_latest() if c.metric == "co2"), None)
    sensors = body_sensors(list_sensors())
    alerts = _open_alerts()
    a = {rid: _alerts_for(rid, alerts) for rid in REGION_IDS}
    return [
        _live_brain(tiles, a["brain"]),
        _live_eyes(now, a["eyes"]),
        _live_heart(tiles["cardiovascular"], latest.get("heart_rate"), a["heart"]),
        _live_lungs(tiles["respiratory"], latest.get("spo2"), latest.get("resp_rate"), co2, a["lungs"]),
        _live_bones(tiles["bone_muscle"], today, a["bones"]),
        radiation_region(today, a["radiation"]),
        _live_temperature(tiles["thermoregulation"], latest.get("skin_temp"), sensors, a["temperature"]),
        sensors_region(sensors, a["sensors"]),
    ]


def twin_state() -> TwinState:
    now = utcnow()
    return TwinState(mission_day=mission_clock(now)[1], simulated=_simulated(), generated_at=iso(now),
                     regions=live_regions(now))


# ---- history (one mission day) -----------------------------------------------------------
def _median(values: list[float]) -> Optional[float]:
    return float(statistics.median(values)) if values else None


def _day_readings(metric: str, start: datetime, end: datetime, good_only: bool = True) -> list[float]:
    where = "metric = ? AND ts >= ? AND ts <= ?" + (" AND quality = 'good'" if good_only else "")
    return [r["value"] for r in db.query("readings", where, (metric, iso(start), iso(end)), order_by="ts")]


def _fires(rule_id: str, ctx: history.BoundedContext) -> bool:
    r = history.rule(rule_id)
    return r is not None and history.fires(r, ctx)


def _hist_brain(day: int, start: datetime, end: datetime, ctx: history.BoundedContext,
                profile: Optional[Profile]) -> TwinRegion:
    nights = [s for s in db.query("sleep_sessions", '"end" >= ? AND "end" <= ?', (iso(start), iso(end)),
                                  order_by="start")]
    tests = db.query("cognitive_tests", "ts >= ? AND ts <= ?", (iso(start), iso(end)), order_by="ts")
    hours = round(sum(n["duration_min"] for n in nights) / 60, 1) if nights else None
    base = profile.baseline.get("pvt_median_ms") if profile else None
    pct = None
    if tests and base is not None and base.mean:
        pct = round((tests[-1]["median_ms"] - base.mean) / base.mean * 100)
    fat, slp = _fires("R-FAT-01", ctx), _fires("R-SLP-01", ctx)
    values = [
        TwinValue(label="Sleep (night ending this day)", value=hours, unit="h" if hours is not None else None),
        TwinValue(label="Attention test vs baseline",
                  value=None if pct is None else f"reaction {'+' if pct > 0 else ''}{pct} %"),
        TwinValue(label="Fatigue pattern", value="Possible · review" if fat else "Not flagged"),
    ]
    if hours is None and pct is None and not (fat or slp):
        return _region("brain", "nodata", NO_DATA, values)
    slower = pct is not None and pct > float(threshold("attention_slower_pct"))
    status = worst("ok", "watch" if slower else None, "watch" if slp else None, "review" if fat else None)
    short_h = float(threshold("sleep_short_hours"))
    sleep_text = None if hours is None else (f"{hours:g} h sleep" + (" (short)" if hours < short_h else ""))
    cog_text = None if pct is None else f"reaction {'+' if pct > 0 else ''}{pct} %"
    rules = [r for r, on in (("R-FAT-01", fat), ("R-SLP-01", slp)) if on]
    return _with_rules(_region("brain", status, _brain_headline(status, sleep_text, cog_text, slp), values), rules)


def _with_rules(region: TwinRegion, rule_ids: list[str]) -> TwinRegion:
    """History: which rule conditions held that day (no alert ids: history creates no alerts)."""
    return region.model_copy(update={"alerts": rule_ids}) if rule_ids else region


def _hist_eyes(end: datetime) -> TwinRegion:
    s = vision.vision_summary(end)
    if s.last_mission_day is None:
        return _region("eyes", "nodata", NO_DATA, [TwinValue(label="Last self-check")])
    status: TwinStatus = "review" if s.status == "review" else ("watch" if s.due else "ok")
    values = [TwinValue(label="Last self-check", value=f"Mission day {s.last_mission_day}", quality="self-check"),
              TwinValue(label="Result vs baseline", value=s.result)]
    headline = {"review": "Possible change reported · review", "watch": "Self-check due"}.get(
        status, f"No change vs baseline (day {s.last_mission_day})")
    return _with_rules(_region("eyes", status, headline, values), ["R-VIS-01"] if status == "review" else [])


def _hist_heart(start: datetime, end: datetime, ctx: history.BoundedContext) -> TwinRegion:
    hr = _median(_day_readings("heart_rate", start, end))
    values = [TwinValue(label="Heart rate (day median)", value=None if hr is None else num(hr, 0),
                        unit="bpm" if hr is not None else None, quality=None if hr is None else "good"),
              TwinValue(label="Rhythm", value=None, quality="missing")]
    if hr is None:
        return _region("heart", "nodata", NO_DATA, values)
    fired = _fires("R-HR-01", ctx)
    status: TwinStatus = "review" if fired else "ok"
    return _with_rules(_region("heart", status, f"{num(hr, 0)} bpm (day median)", values, pulse_bpm=float(num(hr, 0))),
                       ["R-HR-01"] if fired else [])


def _hist_lungs(start: datetime, end: datetime, ctx: history.BoundedContext) -> TwinRegion:
    spo2 = _median(_day_readings("spo2", start, end))
    resp = _median(_day_readings("resp_rate", start, end))
    co2_rows = [r["value"] for r in db.query("cabin_readings", "metric = 'co2' AND ts >= ? AND ts <= ?",
                                             (iso(start), iso(end)))]
    co2 = statistics.fmean(co2_rows) if co2_rows else None
    values = [
        TwinValue(label="SpO₂ (day median)", value=None if spo2 is None else num(spo2, 0), unit="%" if spo2 is not None else None),
        TwinValue(label="Breathing rate (day median)", value=None if resp is None else num(resp, 0),
                  unit="br/min" if resp is not None else None),
        TwinValue(label="Cabin CO₂ (day mean)", value=None if co2 is None else num(co2), unit="mmHg" if co2 is not None else None),
    ]
    if spo2 is None and resp is None:
        return _region("lungs", "nodata", NO_DATA, values)
    spo2_level = history.draft_level(history.rule("R-SPO2-01"), ctx) if history.rule("R-SPO2-01") else None
    co2_fired = _fires("R-CAB-01", ctx)
    status = worst("ok", ("urgent" if spo2_level == "urgent" else "watch") if spo2_level else None,
                   "review" if co2_fired else None)
    parts = [p for p in (f"SpO₂ {num(spo2, 0)} %" if spo2 is not None else None,
                         f"{num(resp, 0)} br/min" if resp is not None else None,
                         f"CO₂ {num(co2)} mmHg" if co2 is not None else None) if p]
    rules = [r for r, on in (("R-SPO2-01", bool(spo2_level)), ("R-CAB-01", co2_fired)) if on]
    return _with_rules(_region("lungs", status, " · ".join(parts), values), rules)


def _hist_bones(day: int, end: datetime) -> TwinRegion:
    """Same counting as bone.week_adherence(day), but only logs written by the end of that day."""
    counts = {"planned": 0, "done": 0, "partial": 0, "skipped": 0, "not_logged": 0}
    for plan in load_plan_items():
        if plan.get("day") is None or not day - 6 <= plan["day"] <= day - 1:
            continue
        counts["planned"] += 1
        rows = db.query("exercise_logs", "plan_id = ? AND ts <= ?", (plan["id"], iso(end)),
                        order_by="ts DESC, rowid DESC", limit=1)
        counts[rows[0]["status"] if rows else "not_logged"] += 1
    logged = counts["done"] + counts["partial"] + counts["skipped"]
    values = [TwinValue(label="Exercise this week",
                        value=f"{counts['done']} done, {counts['partial']} partial of {counts['planned']} planned" if logged else None),
              _bone_estimate_value(day)]
    if not logged:
        return _region("bones", "nodata", NO_DATA + " · no exercise logged", values)
    status: TwinStatus = "ok" if bone.most_days_exercised(counts) else "review"
    return _region("bones", status, f"{counts['done']} done, {counts['partial']} partial this week", values)


def _hist_temperature(end: datetime, profile: Optional[Profile]) -> TwinRegion:
    rows = db.query("readings", "metric = 'skin_temp' AND ts <= ?", (iso(end),), order_by="ts DESC", limit=1)
    if not rows:
        return _region("temperature", "nodata", NO_DATA, [TwinValue(label="Skin temperature", quality="missing")])
    r = rows[0]
    age = (end - parse_ts(r["ts"])).total_seconds() / 60
    fresh = age <= float(threshold("stale_minutes"))
    values = [TwinValue(label="Skin temperature", value=num(r["value"]), unit=r["unit"],
                        quality=r["quality"] if fresh else "stale"),
              TwinValue(label="Last reading", value=ago(age) + " (at the end of the day)" if not fresh else "In this day")]
    if not fresh:
        return _region("temperature", "nodata", f"No data · last {num(r['value'])} {r['unit']} {ago(age)}", values)
    base = profile.baseline.get("skin_temp") if profile else None
    if r["quality"] != "good" or base is None:
        return _region("temperature", "nodata", f"Skin temp {num(r['value'])} {r['unit']} · no usable baseline", values)
    k = float(threshold("hr_sd_multiplier"))  # same multiplier as the Today thermoregulation tile
    outside = r["value"] < base.mean - k * base.sd or r["value"] > base.mean + k * base.sd
    return _region("temperature", "review" if outside else "ok",
                   f"Skin temp {num(r['value'])} {r['unit']} · {'outside' if outside else 'in'} baseline", values)


def _hist_sensors() -> TwinRegion:
    # Only the current connection status is stored (sensors.status + last_seen): no per-day history.
    return _region("sensors", "nodata", "No data · connection history is not stored", [], sensors=[])


def history_regions(day: int, now: datetime, profile: Optional[Profile]) -> tuple[datetime, list[TwinRegion]]:
    start, end = history.day_bounds(day, now)
    ctx = history.BoundedContext(now=end)
    return end, [
        _hist_brain(day, start, end, ctx, profile),
        _hist_eyes(end),
        _hist_heart(start, end, ctx),
        _hist_lungs(start, end, ctx),
        _hist_bones(day, end),
        radiation_region(day),
        _hist_temperature(end, profile),
        _hist_sensors(),
    ]


def twin_timeline(from_day: Optional[int] = None, to_day: Optional[int] = None) -> TwinTimeline:
    now = utcnow()
    today = mission_clock(now)[1]
    to_day = today if to_day is None else min(to_day, today)  # no future days
    from_day = max(0, (to_day - 13) if from_day is None else from_day)
    from_day = min(from_day, to_day)
    profile = _profile()
    days: list[TwinDay] = []
    for d in range(from_day, to_day + 1):
        if d == today:
            days.append(TwinDay(mission_day=d, is_today=True, as_of=iso(now), regions=live_regions(now)))
            continue
        end, regions = history_regions(d, now, profile)
        days.append(TwinDay(mission_day=d, is_today=False, as_of=iso(end), regions=regions))
    return TwinTimeline(from_day=from_day, to_day=to_day, today=today, simulated=_simulated(), days=days)

