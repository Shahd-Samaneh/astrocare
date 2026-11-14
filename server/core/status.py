"""Mission clock, comm schedule and the AppStatus shown in the top bar."""
from __future__ import annotations

from datetime import datetime, timedelta

from . import db
from .config import app_config, format_met, iso, parse_met, utcnow
from .models import AppStatus
from .seed import seeded_at


def _elapsed_seconds(now: datetime | None = None) -> float:
    d, h, m = parse_met(db.get_meta("met_at_seed") or app_config()["mission"]["met_at_seed"])
    return ((now or utcnow()) - seeded_at()).total_seconds() + (d * 1440 + h * 60 + m) * 60


def mission_clock(now: datetime | None = None) -> tuple[str, int]:
    """(MET as 'DDD:HH:MM', mission day). The clock runs from the seed time."""
    e = _elapsed_seconds(now)
    return format_met(e), int(e // 86400)


def mission_day_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now - timedelta(seconds=_elapsed_seconds(now) % 86400)


def next_comm_window(now: datetime | None = None) -> str:
    w = app_config()["comms"]["window"]
    start = seeded_at() + timedelta(minutes=int(w["first_after_seed_minutes"]))
    period, dur = timedelta(hours=float(w["every_hours"])), timedelta(minutes=int(w["duration_minutes"]))
    now = now or utcnow()
    while start + dur < now:
        start += period
    return iso(start)


def build_status() -> AppStatus:
    cfg = app_config()
    comms = cfg["comms"]
    met, day = mission_clock()
    return AppStatus(
        mission_name=cfg["mission"]["name"],
        mission_day=day,
        met=met,
        local_mode=bool(comms["local_mode"]),
        next_comm_window_ts=next_comm_window(),
        signal_delay_sec=int(comms["signal_delay_sec"]),
        last_sync_ts=iso(seeded_at() - timedelta(days=float(comms["last_sync_days_ago"]))),
        outbox_count=db.count("reports", "status = 'queued'"),
        simulated=db.count("readings", "source = 'simulated'") > 0,
        crew_name=cfg["crew"]["name"],
        crew_initials=cfg["crew"]["initials"],
    )
