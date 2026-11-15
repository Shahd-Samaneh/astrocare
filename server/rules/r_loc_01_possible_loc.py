# Owner: Shahd
"""R-LOC-01 · Possible loss of consciousness: check crew member now.

In microgravity nobody falls, so there is no fall sensor to rely on. The rule looks for
at least `loc.min_signals` (2) of these 4 signals, each starting inside the last
`loc.window_seconds` (60 s):

  hr_change   a good-quality heart-rate reading differs by more than `loc.hr_change_pct`
              from the median of the good readings in the `loc.hr_median_seconds` before it
              (needs at least `loc.min_stream_readings` readings in that median)
  chest_gap   the chest strap was streaming (>= min_stream_readings good readings in the
              hr_median_seconds before its last reading), then sent nothing for
              `loc.signal_gap_seconds`
  no_motion   the wrist sensor showed movement (>= `loc.motion_min_g`), then only still
              samples for `loc.no_motion_seconds`, while samples kept arriving
  low_spo2    a good-quality SpO2 reading below the existing `spo2_min`

Low-quality readings never count (HR, SpO2 and motion use good readings only, and a chest
gap needs a good-quality stream before it), so low-quality data alone can't fire the rule.
The 30-min seeded vitals and the 5-min live feed are too sparse to count as a stream.

Level: 'urgent' (the contract has no 'emergency' level). The emergency handling (Watch,
"Are you OK?", escalation) is in server/features/crew/. See docs/loc-notes.md.
It never says "fainted", never diagnoses, and gives no treatment advice: the only clinical
step is locked for the CMO. At most one open alert per crew member (dedupe key), and signals
already covered by an earlier R-LOC-01 alert never fire it again.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from server.core import db
from server.core.config import app_config, iso, parse_ts
from server.core.models import NextStep
from server.features.crew.store import motion_samples
from server.features.crew.thresholds import loc_threshold

from .base import AlertDraft, Rule, RuleContext

TITLE = "Possible loss of consciousness: check crew member now"
POSSIBLE_FACTORS = [
    "Sensor detached or moved (not confirmed)",
    "Sleeping or resting quietly (not confirmed)",
    "Loss of consciousness (not confirmed)",
    "Other cause (not confirmed)",
]


@dataclass
class Signal:
    kind: str  # 'hr_change' | 'chest_gap' | 'no_motion' | 'low_spo2'
    label: str
    ts: datetime
    detail: str
    data_used: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"kind": self.kind, "label": self.label, "ts": iso(self.ts), "detail": self.detail}


def _hhmmss(dt: datetime) -> str:
    return f"{iso(dt)[11:19]} UTC"


def _good(readings, astronaut_id: str):
    return [r for r in readings if r.quality == "good" and r.astronaut_id == astronaut_id]


def find_signals(
    ctx: RuleContext, astronaut_id: str, ignore_before: datetime | None,
    fmt_time: Callable[[datetime], str] = _hhmmss,
) -> tuple[list[Signal], list[str]]:
    """The signals present at ctx.now, and the sensors without data in the window.

    `fmt_time` formats the times inside the texts: "HH:MM:SS UTC" for the alert (shown on other
    teams' pages), ISO for the crew API (the Crew alerts page shows them in local time).
    """
    now = ctx.now
    window = timedelta(seconds=float(loc_threshold("window_seconds")))
    median_span = timedelta(seconds=float(loc_threshold("hr_median_seconds")))
    min_stream = int(loc_threshold("min_stream_readings"))
    gap = timedelta(seconds=float(loc_threshold("signal_gap_seconds")))
    still = timedelta(seconds=float(loc_threshold("no_motion_seconds")))
    start = now - window
    lookback_h = (window + median_span + gap + still).total_seconds() / 3600 + 0.01

    def in_window(t: datetime) -> bool:
        # signals at or before an earlier R-LOC-01 alert were already handled by that alert
        return start <= t <= now and (ignore_before is None or t > ignore_before)

    signals: list[Signal] = []
    missing: list[str] = []

    # 1. heart-rate change vs the median of the previous 5 minutes
    hr = [r for r in _good(ctx.readings("heart_rate", hours=lookback_h), astronaut_id) if parse_ts(r.ts) <= now]
    pct_limit = float(loc_threshold("hr_change_pct"))
    for r in hr:
        t = parse_ts(r.ts)
        if not in_window(t):
            continue
        prev = [p.value for p in hr if t - median_span <= parse_ts(p.ts) < t]
        if len(prev) < min_stream:
            continue
        med = median(prev)
        if med <= 0:
            continue
        pct = (r.value - med) / med * 100
        if abs(pct) > pct_limit:
            word = "dropped" if pct < 0 else "rose"
            signals.append(Signal(
                "hr_change", "Heart-rate change", t,
                f"Heart rate {word} to {r.value:.0f} {r.unit} "
                f"({pct:+.0f} % vs the {median_span.total_seconds() / 60:.0f}-min median of {med:.0f} {r.unit}).",
                [r.id],
            ))
            break

    # 2. chest strap stopped sending
    chest = ctx.sensor_for("heart_rate")
    if chest:
        chest_rows = []
        for metric in chest.metrics:
            chest_rows += [r for r in ctx.readings(metric, hours=lookback_h)
                           if r.astronaut_id == astronaut_id and parse_ts(r.ts) <= now]
        chest_rows.sort(key=lambda r: r.ts)
        last = parse_ts(chest_rows[-1].ts) if chest_rows else None
        if last is None or last < now - window:
            since = f"since {fmt_time(last)}" if last else "in the last hour"
            missing.append(f"{chest.name} ({chest.id}): no data {since}.")
        if last is not None and now - last >= gap and in_window(last + gap):
            stream = [r for r in chest_rows if r.quality == "good" and last - median_span <= parse_ts(r.ts) <= last]
            if len(stream) >= min_stream:
                signals.append(Signal(
                    "chest_gap", "Chest sensor signal lost", last + gap,
                    f"{chest.name} was streaming, then sent nothing after {fmt_time(last)} "
                    f"({(now - last).total_seconds():.0f} s so far).",
                    [chest_rows[-1].id],
                ))

    # 3. wrist: movement, then stillness while samples keep arriving
    wrist_id = (ctx.sensor_for("spo2").id if ctx.sensor_for("spo2") else "s-wrist")
    motion = [m for m in motion_samples(astronaut_id, now - timedelta(hours=lookback_h), now) if m["quality"] == "good"]
    min_g = float(loc_threshold("motion_min_g"))
    if not motion or parse_ts(motion[-1]["ts"]) < now - window:
        missing.append(f"Wrist motion ({wrist_id}): no motion samples in the last {window.total_seconds():.0f} s.")
    else:
        moving = [m for m in motion if m["value_g"] >= min_g]
        if moving:
            last_move = parse_ts(moving[-1]["ts"])
            still_rows = [m for m in motion if parse_ts(m["ts"]) > last_move]
            arriving = parse_ts(motion[-1]["ts"]) >= now - gap
            if still_rows and arriving and now - last_move >= still and in_window(last_move + still):
                signals.append(Signal(
                    "no_motion", "No wrist movement", last_move + still,
                    f"Wrist sensor showed movement until {fmt_time(last_move)}, then no movement for "
                    f"{(now - last_move).total_seconds():.0f} s (samples still arriving).",
                    [moving[-1]["id"], still_rows[-1]["id"]],
                ))

    # 4. SpO2 below the existing threshold, good quality only
    spo2_min = float(ctx.threshold("spo2_min"))
    spo2 = [r for r in ctx.readings("spo2", hours=lookback_h) if r.astronaut_id == astronaut_id and parse_ts(r.ts) <= now]
    if not [r for r in spo2 if parse_ts(r.ts) >= now - window]:
        missing.append(f"SpO₂ ({wrist_id}): no reading in the last {window.total_seconds():.0f} s.")
    for r in _good(spo2, astronaut_id):
        t = parse_ts(r.ts)
        if in_window(t) and r.value < spo2_min:
            signals.append(Signal(
                "low_spo2", "Low SpO₂", t,
                f"SpO₂ {r.value:.0f}{r.unit}, below {spo2_min:.0f}{r.unit} (good quality).",
                [r.id],
            ))
            break

    signals.sort(key=lambda s: s.ts)
    return signals, missing


def last_loc_alert_ts(astronaut_id: str) -> datetime | None:
    rows = db.query("alerts", "rule_id = ? AND dedupe_key = ?", (PossibleLocRule.id, f"loc-{astronaut_id}"),
                    order_by="ts DESC", limit=1)
    return parse_ts(rows[0]["ts"]) if rows else None


class PossibleLocRule(Rule):
    id = "R-LOC-01"
    name = "Possible loss of consciousness"
    sources = [
        "config/thresholds.yaml: loc.* (all experimental values), spo2_min (experimental)",
        "Signals plus no response, not a fall sensor (microgravity): docs/loc-notes.md",
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        astronaut_id = ctx.astronaut_id or str(app_config().get("crew", {}).get("astronaut_id", "c2"))
        signals, missing = find_signals(ctx, astronaut_id, ignore_before=last_loc_alert_ts(astronaut_id))
        if len(signals) < int(loc_threshold("min_signals")):
            return None
        window_s = float(loc_threshold("window_seconds"))
        data_used = [rid for s in signals for rid in s.data_used]
        data_used.append(f"Window {iso(ctx.now - timedelta(seconds=window_s))}–{iso(ctx.now)}")
        return AlertDraft(
            level="urgent",
            title=TITLE,
            what_changed=" ".join(f"{s.label} at {_hhmmss(s.ts)}: {s.detail}" for s in signals),
            data_used=data_used,
            missing=missing,
            possible_factors=POSSIBLE_FACTORS,
            next_steps=[
                NextStep(text="Go to the crew member now and check whether they respond"),
                NextStep(text="Check that the chest strap and wrist sensor are attached"),
                NextStep(text="CMO: medical assessment and any treatment decision", locked_for_cmo=True),
            ],
            dedupe_key=f"loc-{astronaut_id}",
        )
