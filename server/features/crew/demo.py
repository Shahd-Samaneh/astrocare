# Owner: Shahd
"""Demo only: inject simulated readings that meet R-LOC-01 "now", then run the engine.

Shown in the UI only when config/app.yaml has `demo: true`; the endpoint refuses otherwise.
Every injected row is source 'simulated' with an id starting 'demo-loc-'.

Timeline relative to `now` (with the starting thresholds):
  heart rate   ~72 bpm every 10 s for 6 min, then 41 and 40 bpm at -35 s and -25 s  -> hr_change
  chest strap  nothing after -25 s (gap 20 s reached at -5 s)                      -> chest_gap
  wrist motion moving (0.12-0.18 g) every 5 s until -40 s, then still (0.01 g)
               up to now (30 s of stillness reached at -10 s)                       -> no_motion
  SpO2         not touched (3 of the 4 signals)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from server.core import db
from server.core.config import iso
from server.rules.base import RuleContext
from server.rules.engine import run_rules

from . import store


def inject(now: datetime) -> None:
    astronaut_id, _ = store.crew_member()
    hr = []
    t = now - timedelta(minutes=6)
    i = 0
    while t <= now - timedelta(seconds=45):
        hr.append((t, 72 + (i % 3) - 1))
        t += timedelta(seconds=10)
        i += 1
    hr += [(now - timedelta(seconds=35), 41), (now - timedelta(seconds=25), 40)]
    db.insert_many("readings", [
        {"id": db.new_id("demo-loc-hr"), "astronaut_id": astronaut_id, "metric": "heart_rate", "value": float(v),
         "unit": "bpm", "ts": iso(ts), "source": "simulated", "quality": "good"}
        for ts, v in hr
    ])
    motion = []
    t = now - timedelta(minutes=6)
    i = 0
    while t <= now:
        moving = t <= now - timedelta(seconds=40)
        motion.append({
            "id": db.new_id("demo-loc-mot"), "astronaut_id": astronaut_id, "sensor_id": "s-wrist", "ts": iso(t),
            "value_g": (0.12 + 0.02 * (i % 4)) if moving else 0.01, "quality": "good", "source": "simulated",
        })
        t += timedelta(seconds=5)
        i += 1
    store.add_motion(motion)


def trigger(now: datetime) -> str | None:
    """Inject, run the engine, open the Watch. Returns the new R-LOC-01 alert id (None if none fired)."""
    store.sync(now)
    inject(now)
    db.log_action("system", "crew_loc:demo_inject")
    created = [a for a in run_rules(RuleContext(now=now)) if a.rule_id == store.RULE_ID]
    store.sync(now)
    return created[0].id if created else None
