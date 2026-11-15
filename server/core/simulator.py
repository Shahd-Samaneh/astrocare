"""Simulated mission data for one astronaut ("Crew Member 2", initials C2).

`generate(now)` returns {table_name: [row, ...]} in the contract shape (snake_case
keys = DB columns). Everything is marked source='simulated'. Deterministic for a
given `random_seed` in config/app.yaml.

Baked-in demo scenario (mission day 142 is "today", the last simulated day):
  * nights 141 and 142 are short (~5 h)
  * the last two attention tests have a median ~20 % slower than baseline
  * skin temperature is stale: last value 6 h ago, its sensor is "disconnected"
  * no blood pressure reading today (missing)
  * no check-in today (R-FAT-01 lists it as missing)
  * the outbox is empty (earlier reports are already sent)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .config import SIM_DIR, app_config, iso, parse_met

UNITS = {
    "heart_rate": "bpm", "spo2": "%", "skin_temp": "°C", "bp_sys": "mmHg", "bp_dia": "mmHg",
    "resp_rate": "br/min", "co2": "mmHg", "cabin_temp": "°C", "noise": "dBA", "humidity": "%",
}


def load_json(name: str) -> Any:
    with open(SIM_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _camel_to_snake(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if k.startswith("_"):
            continue
        sk = "".join(f"_{c.lower()}" if c.isupper() else c for c in k)
        out[sk] = [_camel_to_snake(x) if isinstance(x, dict) else x for x in v] if isinstance(v, list) else v
    return out


def generate(now: datetime) -> dict[str, list[dict[str, Any]]]:
    cfg = app_config()
    sim = cfg.get("simulator", {})
    rng = np.random.default_rng(int(sim.get("random_seed", 42)))
    n_days = int(sim.get("days", 14))
    crew = cfg["crew"]
    aid = crew["astronaut_id"]

    today, h, m = parse_met(cfg["mission"]["met_at_seed"])
    first_day = today - n_days + 1

    def day_start(d: int) -> datetime:
        """Start (00:00 mission time) of mission day d."""
        return now - timedelta(hours=h, minutes=m) - timedelta(days=today - d)

    start = day_start(first_day)
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in (
        "readings", "cabin_readings", "sensors", "profiles", "sleep_sessions", "cognitive_tests",
        "checkins", "exercise_plans", "exercise_logs", "resources", "relax_sessions", "reports",
        "action_log", "vision_checks",
    )}

    def quality() -> str:
        return "low" if rng.random() < 0.02 else "good"

    # ---- sleep windows (needed for heart-rate dips) ---------------------------
    sleeps = []
    for d in range(first_day, today + 1):
        short = d >= today - 1
        if short:  # nights 141 and 142: late bedtime, ~5 h
            s = day_start(d) + timedelta(minutes=30 + float(rng.normal(0, 10)))
            dur = 300 + float(rng.normal(0, 8))
        else:
            s = day_start(d) - timedelta(minutes=90 + float(rng.normal(0, 15)))
            dur = 440 + float(rng.normal(0, 20))
        e = s + timedelta(minutes=dur)
        sleeps.append((s, e))
        out["sleep_sessions"].append({
            "id": f"sleep-{d}", "start": iso(s), "end": iso(e), "duration_min": int(round(dur)),
            "awakenings": int(rng.integers(3, 5) if short else rng.integers(0, 3)),
            "self_quality": 2 if short else int(rng.integers(3, 6)), "source": "simulated",
        })

    def asleep(t: datetime) -> bool:
        return any(s <= t <= e for s, e in sleeps)

    # ---- vitals every 30 min -------------------------------------------------
    skin_cutoff = now - timedelta(hours=6)
    t, i = start, 0
    while t <= now:
        hour = (t - day_start(first_day)).total_seconds() / 3600 % 24
        circ = np.sin((hour - 9) / 24 * 2 * np.pi)
        sl = asleep(t)
        vals = {
            "heart_rate": 66 + 5 * circ - (8 if sl else 0) + rng.normal(0, 2.5),
            "spo2": min(100.0, 97.6 + rng.normal(0, 0.5)),
            "resp_rate": 14 - (1.5 if sl else 0) + rng.normal(0, 0.9),
        }
        if t <= skin_cutoff:
            vals["skin_temp"] = 33.8 + 0.3 * circ + rng.normal(0, 0.15)
        for metric, v in vals.items():
            out["readings"].append({
                "id": f"r-{metric}-{i}", "astronaut_id": aid, "metric": metric,
                "value": round(float(v), 1), "unit": UNITS[metric], "ts": iso(t),
                "source": "simulated", "quality": quality(),
            })
        t += timedelta(minutes=30)
        i += 1
    # make sure the stale skin_temp reading is exactly ~6 h old
    out["readings"].append({
        "id": "r-skin_temp-last", "astronaut_id": aid, "metric": "skin_temp", "value": 33.9,
        "unit": "°C", "ts": iso(skin_cutoff), "source": "simulated", "quality": "good",
    })

    # ---- blood pressure twice a day, none on today ---------------------------
    for d in range(first_day, today):
        for hh in (7, 19):
            ts = iso(day_start(d) + timedelta(hours=hh, minutes=int(rng.integers(0, 20))))
            sys_v, dia_v = 117 + rng.normal(0, 5), 76 + rng.normal(0, 4)
            for metric, v in (("bp_sys", sys_v), ("bp_dia", dia_v)):
                out["readings"].append({
                    "id": f"r-{metric}-{d}-{hh}", "astronaut_id": aid, "metric": metric,
                    "value": round(float(v)), "unit": "mmHg", "ts": ts,
                    "source": "simulated", "quality": "good",
                })

    # ---- cabin hourly ---------------------------------------------------------
    t, i = start, 0
    while t <= now:
        for metric, base, sd in (("co2", 2.6, 0.3), ("cabin_temp", 22.5, 0.4),
                                 ("noise", 58, 2.5), ("humidity", 45, 3)):
            out["cabin_readings"].append({
                "id": f"c-{metric}-{i}", "metric": metric, "value": round(float(base + rng.normal(0, sd)), 1),
                "unit": UNITS[metric], "ts": iso(t), "source": "simulated",
            })
        t += timedelta(hours=1)
        i += 1

    # ---- sensors --------------------------------------------------------------
    last_bp = iso(day_start(today - 1) + timedelta(hours=19, minutes=20))
    out["sensors"] = [
        {"id": "s-chest", "name": "Chest strap", "location": "Torso", "metrics": ["heart_rate", "resp_rate"],
         "status": "connected", "last_seen": iso(now)},
        {"id": "s-wrist", "name": "Wrist oximeter", "location": "Left wrist", "metrics": ["spo2"],
         "status": "connected", "last_seen": iso(now)},
        {"id": "s-skin", "name": "Skin temperature patch", "location": "Upper arm", "metrics": ["skin_temp"],
         "status": "disconnected", "last_seen": iso(skin_cutoff)},
        {"id": "s-bp", "name": "Blood pressure cuff", "location": "Medical kit", "metrics": ["bp_sys", "bp_dia"],
         "status": "low_battery", "last_seen": last_bp},
        {"id": "s-cabin", "name": "Cabin environment monitor", "location": "Habitat module",
         "metrics": ["co2", "cabin_temp", "noise", "humidity"], "status": "connected", "last_seen": iso(now)},
    ]

    # ---- attention tests (5-trial reaction test), one per morning --------------
    base_median = 285.0
    for d in range(first_day, today + 1):
        slow = d >= today - 1
        target = base_median * 1.2 if slow else base_median + rng.normal(0, 8)
        offsets = np.array([-30, -12, 0, 14, 38]) + rng.normal(0, 4, 5)
        offsets[2] = 0
        trials = [round(float(target + o)) for o in offsets]
        if slow and d == today:
            trials[-1] = 540  # one lapse today
        rng.shuffle(trials)
        out["cognitive_tests"].append({
            "id": f"pvt-{d}", "ts": iso(day_start(d) + timedelta(hours=6, minutes=40)),
            "trials_ms": trials, "median_ms": float(np.median(trials)),
            "lapses": sum(1 for x in trials if x > 500), "false_starts": 1 if slow and d == today else 0,
        })

    # ---- check-ins -------------------------------------------------------------
    for d in range(first_day, today):  # no check-in today: the demo shows it as missing
        skipped = d == first_day + 6
        late = d >= today - 1
        out["checkins"].append({
            "id": f"ci-{d}", "ts": iso(day_start(d) + timedelta(hours=7)),
            "mood": None if skipped else (3 if late else int(rng.integers(3, 5))),
            "stress": None if skipped else (4 if late else int(rng.integers(1, 3))),
            "note_private": None, "skipped": skipped,
        })

    # ---- baseline from the first 10 days ----------------------------------------
    cut = iso(day_start(first_day + 10))
    baseline: dict[str, dict[str, float]] = {}
    for metric in ("heart_rate", "spo2", "skin_temp", "bp_sys", "bp_dia", "resp_rate"):
        vals = np.array([r["value"] for r in out["readings"] if r["metric"] == metric and r["ts"] < cut])
        baseline[metric] = {"mean": round(float(vals.mean()), 2), "sd": round(float(vals.std(ddof=1)), 2), "n": int(len(vals))}
    pvt = np.array([t["median_ms"] for t in out["cognitive_tests"] if t["ts"] < cut])
    baseline["pvt_median_ms"] = {"mean": round(float(pvt.mean()), 1), "sd": round(float(pvt.std(ddof=1)), 1), "n": int(len(pvt))}
    sl = np.array([s["duration_min"] / 60 for s in out["sleep_sessions"] if s["start"] < cut])
    baseline["sleep_hours"] = {"mean": round(float(sl.mean()), 2), "sd": round(float(sl.std(ddof=1)), 2), "n": int(len(sl))}

    out["profiles"] = [{
        "id": aid, "name": crew["name"], "mission_day": today,
        "allergies": ["Penicillin"],
        "current_meds": ["Vitamin D3 supplement (daily)"],
        "history": ["Seasonal allergic rhinitis", "Left knee ligament strain (pre-flight, resolved)"],
        "baseline": baseline,
    }]

    # ---- static JSON: resources, exercise plan ---------------------------------
    out["resources"] = [_camel_to_snake(r) for r in load_json("resources.json")["resources"]]
    out["exercise_plans"] = [_camel_to_snake(p) for p in load_json("exercise_plan.json")["plans"]]
    out["exercise_logs"] = [
        {"id": "exl-140", "plan_id": "ex-140", "ts": iso(day_start(140) + timedelta(hours=15)),
         "status": "done", "reason": None, "alternative_id": None},
        {"id": "exl-141", "plan_id": "ex-141", "ts": iso(day_start(141) + timedelta(hours=15)),
         "status": "partial", "reason": "fatigue", "alternative_id": "alt-141-b"},
    ]

    # ---- relax, reports, action log -------------------------------------------------
    for k, d in enumerate((136, 139, 141)):
        out["relax_sessions"].append({
            "id": f"relax-{d}", "ts": iso(day_start(d) + timedelta(hours=21)),
            "scene_id": ["forest-stream", "ocean-shore", "night-sky"][k],
            "audio_mode": ["nature", "music", "nature"][k], "duration_min": [10, 15, 10][k],
            "stress_before": [3, 3, 4][k], "stress_after": [2, 2, 3][k],
        })
    # ---- vision self-check: a baseline (day 130) and a repeat (day 137), both "no change" ------
    # No rng here, so adding these rows leaves every other simulated value unchanged.
    out["vision_checks"] = [
        {"id": f"vis-{d}", "ts": iso(day_start(d) + timedelta(hours=8, minutes=15)), "eye": "both",
         "near_vision_smallest_line": 8, "amsler_changed": False, "notes": None, "source": "simulated"}
        for d in (130, 137)
    ]
    # past reports are already sent, so the outbox starts empty after a reseed
    out["reports"] = [
        {"id": "rep-135", "created_ts": iso(day_start(135) + timedelta(hours=18)), "status": "sent",
         "sections": [{"id": "s1", "title": "Weekly health summary", "body": "All metrics within personal baseline."}],
         "file_path": None},
        {"id": "rep-141", "created_ts": iso(day_start(141) + timedelta(hours=18)), "status": "sent",
         "sections": [{"id": "s1", "title": "Weekly health summary", "body": "Short sleep on night 141."}],
         "file_path": None},
        {"id": "rep-142", "created_ts": iso(day_start(142) + timedelta(hours=6, minutes=50)), "status": "sent",
         "sections": [{"id": "s1", "title": "Sleep and attention note", "body": "Two short nights; attention test slower than baseline."}],
         "file_path": None},
    ]
    out["action_log"] = [{"id": "act-seed", "ts": iso(now), "actor": "system", "action": "seed_simulated_data", "ref_id": None}]
    return out
