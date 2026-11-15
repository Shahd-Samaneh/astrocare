"""Live feed (demo only): keeps the continuous vitals fresh while the server runs.

Without it, HR / SpO2 / respiration go stale `stale_minutes` (2 h) after a reseed, because the
simulator only writes history up to the seed instant. While the server runs, this adds one
simulated reading every `every_minutes` for heart rate, SpO2 and respiration rate:

  * source "simulated", quality "good"
  * value inside the personal baseline mean ± `band_sd` SD (0.5), so no rule can fire from it
    (R-HR-01 needs > mean + 2 SD, R-SPO2-01 needs < spo2_min)
  * NEVER skin temperature (must stay stale) or blood pressure (must stay missing)
  * it does not run the rule engine, so R-FAT-01 and the stale/missing story are unchanged

Cabin: every `cabin_every_minutes` (15) it also adds one simulated cabin reading per metric
(CO2, temperature, noise, humidity), close to the latest *seeded* value (+ normal noise of
`cabin_jitter_sd` × that metric's seeded SD), then clamped inside the thresholds.yaml limits:
  * co2 ≤ co2_max − 0.1, so no feed reading can push the 1-hour average over co2_max
    (R-CAB-01 can't fire from the feed)
  * cabin_temp / humidity inside [min + 0.1, max − 0.1] (R-CAB-02 can't fire from the feed)
  * noise inside the rolling noise baseline mean ± band_sd·SD (same window as the Today status;
    R-CAB-03 needs > mean + 2 SD, so it can't fire from the feed)

Config: config/app.yaml → simulator.live_feed {enabled, every_minutes, band_sd,
cabin_every_minutes, cabin_jitter_sd}. Always off under
pytest and with ASTROCARE_NO_LIVE_FEED=1. A heartbeat in `meta` (live_feed_heartbeat) lets
scripts/demo_state.py show that the feed is running.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from . import db
from .config import app_config, iso, parse_ts, threshold, utcnow
from .simulator import UNITS

log = logging.getLogger("astrocare.live_feed")

LIVE_METRICS = ("heart_rate", "spo2", "resp_rate")  # never skin_temp, bp_sys, bp_dia
CABIN_LIVE_METRICS = ("co2", "cabin_temp", "noise", "humidity")
STEP = 0.1  # readings are rounded to 0.1; limits are kept one step away
HEARTBEAT_KEY = "live_feed_heartbeat"
LOOP_SECONDS = 60  # how often the loop wakes; a reading is only added when one is due
_rng = np.random.default_rng()


def settings() -> dict[str, Any]:
    cfg = (app_config().get("simulator") or {}).get("live_feed") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "every_minutes": float(cfg.get("every_minutes", 5)),
        "band_sd": float(cfg.get("band_sd", 0.5)),
        "cabin_every_minutes": float(cfg.get("cabin_every_minutes", 15)),
        "cabin_jitter_sd": float(cfg.get("cabin_jitter_sd", 0.25)),
    }


def feed_enabled() -> bool:
    if "pytest" in sys.modules or os.environ.get("ASTROCARE_NO_LIVE_FEED") == "1":
        return False
    return settings()["enabled"]


def _baseline() -> dict[str, dict[str, float]]:
    rows = db.query("profiles", limit=1)
    return (rows[0].get("baseline") or {}) if rows else {}


def _value(mean: float, sd: float, band_sd: float) -> float:
    """A value inside mean ± band_sd·SD, rounded to 0.1 without leaving the band."""
    lo, hi = mean - band_sd * sd, mean + band_sd * sd
    v = round(float(_rng.uniform(lo, hi)), 1)
    return min(max(v, math.ceil(lo * 10) / 10), math.floor(hi * 10) / 10)


def _cabin_bounds(metric: str, now: datetime, band_sd: float) -> tuple[float | None, float | None]:
    """Safe (lo, hi) for a feed value: strictly inside every limit the Today status / R-CAB-01 use."""
    if metric == "co2":
        hi = threshold("co2_max")
        return 0.0, (None if hi is None else float(hi) - STEP)
    if metric in ("cabin_temp", "humidity"):
        lo, hi = threshold(f"{metric}_min"), threshold(f"{metric}_max")
        return (None if lo is None else float(lo) + STEP), (None if hi is None else float(hi) - STEP)
    if metric == "noise":  # same baseline window as GET /cabin/latest
        since = iso(now - timedelta(days=float(threshold("noise_baseline_days"))))
        values = [r["value"] for r in db.query("cabin_readings", "metric = ? AND ts >= ?", ("noise", since))]
        if len(values) < 2:
            return None, None
        mean, sd = float(np.mean(values)), float(np.std(values, ddof=1))
        return mean - band_sd * sd, mean + band_sd * sd
    return None, None


def _clamp(v: float, lo: float | None, hi: float | None) -> float:
    if lo is not None:
        v = max(v, math.ceil(round(lo / STEP, 6)) * STEP)
    if hi is not None:
        v = min(v, math.floor(round(hi / STEP, 6)) * STEP)
    return round(v, 1)


def _cabin_tick(now: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    due_after = timedelta(minutes=cfg["cabin_every_minutes"]) - timedelta(seconds=5)
    added = []
    for metric in CABIN_LIVE_METRICS:
        last = db.query("cabin_readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        if last and now - parse_ts(last[0]["ts"]) < due_after:
            continue
        seeded = [r["value"] for r in db.query("cabin_readings", "metric = ? AND id NOT LIKE 'live-%'", (metric,))]
        if not seeded:
            continue  # nothing to stay close to
        anchor = db.query("cabin_readings", "metric = ? AND id NOT LIKE 'live-%'", (metric,),
                          order_by="ts DESC", limit=1)[0]["value"]
        sd = float(np.std(seeded, ddof=1)) if len(seeded) > 1 else 0.0
        raw = float(anchor) + float(_rng.normal(0, cfg["cabin_jitter_sd"] * sd))
        row = {
            "id": db.new_id(f"live-{metric}"), "metric": metric,
            "value": _clamp(raw, *_cabin_bounds(metric, now, cfg["band_sd"])),
            "unit": UNITS[metric], "ts": iso(now), "source": "simulated",
        }
        db.insert("cabin_readings", row)
        added.append(row)
    return added


def tick(now: datetime | None = None) -> list[dict[str, Any]]:
    """Add one reading per live metric whose latest reading is at least `every_minutes` old, and one
    cabin reading per metric whose latest is at least `cabin_every_minutes` old.
    Returns the rows added (vitals rows have `quality`, cabin rows don't). Safe to call often."""
    now = now or utcnow()
    cfg = settings()
    base = _baseline()
    rows = db.query("profiles", limit=1)
    astronaut_id = rows[0]["id"] if rows else "c2"
    due_after = timedelta(minutes=cfg["every_minutes"]) - timedelta(seconds=5)
    added = []
    for metric in LIVE_METRICS:
        b = base.get(metric)
        if not b:
            continue
        last = db.query("readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        if last and now - parse_ts(last[0]["ts"]) < due_after:
            continue
        row = {
            "id": db.new_id(f"live-{metric}"), "astronaut_id": astronaut_id, "metric": metric,
            "value": _value(float(b["mean"]), float(b["sd"]), cfg["band_sd"]), "unit": UNITS[metric],
            "ts": iso(now), "source": "simulated", "quality": "good",
        }
        db.insert("readings", row)
        added.append(row)
    added += _cabin_tick(now, cfg)
    db.set_meta(HEARTBEAT_KEY, iso(now))
    return added


async def run_forever() -> None:
    cfg = settings()
    log.info("Live feed on: HR, SpO2, resp every %s min; cabin every %s min (simulated)",
             cfg["every_minutes"], cfg["cabin_every_minutes"])
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001 - the demo feed must never take the server down
            log.exception("Live feed tick failed")
        await asyncio.sleep(LOOP_SECONDS)
