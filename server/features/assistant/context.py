"""User context for the assistant: latest alerts + a 7-day summary, filtered by permissions.

Data comes only from the existing endpoints (called in-process as functions):
  alerts      GET /api/alerts                  (monitoring)
  vitals      GET /api/readings/latest         (monitoring)
  sleep       GET /api/sleep?nights=7          (daily)
  tests       GET /api/tests                   (daily)
  check-ins   GET /api/checkins                (daily, only if assistant.checkins is on)
  exercise    GET /api/exercise/plan + /api/today/plan (daily)

If a source fails (endpoint not merged yet), its part of mock_context.json is used instead.
ASTROCARE_ASSISTANT_MOCK=1 forces the mock for every source (tests).

Never sent to the model: `notePrivate`, and next steps locked for the CMO (they may name a medicine).
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from server.core.config import parse_ts, threshold, utcnow

from .permissions import get_permissions

MOCK_PATH = Path(__file__).with_name("mock_context.json")
DAYS = 7
MAX_ALERTS = 3


def _mock() -> dict[str, Any]:
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


def _dump(items: Any) -> Any:
    """Pydantic models -> camelCase dicts (the JSON the endpoint would return)."""
    if isinstance(items, list):
        return [_dump(i) for i in items]
    if hasattr(items, "model_dump"):
        return items.model_dump(by_alias=True)
    return items


def _sources() -> dict[str, Callable[[], Any]]:
    from server.features.daily import router as daily
    from server.features.monitoring import router as monitoring

    return {
        "alerts": lambda: monitoring.list_alerts(status=None),
        "latestReadings": monitoring.latest_readings,
        "sleep": lambda: daily.list_sleep(nights=DAYS),
        "tests": lambda: daily.list_tests(n=14),
        "checkins": lambda: daily.list_checkins(n=14),
        "exercisePlan": daily.exercise_plan,
        "todayPlan": daily.today_plan,
    }


def load_raw(needed: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Raw endpoint data for the needed sources. Returns (data, names that came from the mock)."""
    force_mock = os.environ.get("ASTROCARE_ASSISTANT_MOCK") == "1"
    mock = None
    out: dict[str, Any] = {}
    mocked: list[str] = []
    sources = {} if force_mock else _sources()
    for name in needed:
        try:
            if force_mock:
                raise LookupError("mock forced")
            out[name] = _dump(sources[name]())
        except Exception:  # noqa: BLE001  any failure -> mock for this source only
            mock = mock if mock is not None else _mock()
            out[name] = mock.get(name)
            mocked.append(name)
    return out, mocked


def _within_days(items: list[dict], key: str, days: int = DAYS) -> list[dict]:
    if not items:
        return []
    stamps = [parse_ts(i[key]) for i in items if i.get(key)]
    # relative to the newest item for mock data, to now for live data
    ref = max([utcnow(), *stamps]) if stamps else utcnow()
    since = ref - timedelta(days=days)
    return [i for i in items if i.get(key) and parse_ts(i[key]) >= since]


def _age(minutes: int | None) -> str | None:
    """Reading age rounded to 10 minutes, e.g. 'about 2 h 10 m'. Coarse on purpose: the
    user-data part of the prompt then stays identical between questions (prompt cache)."""
    if minutes is None:
        return None
    m = int(round(minutes / 10.0) * 10)
    return f"about {m} m" if m < 60 else f"about {m // 60} h {m % 60:02d} m"


def _hm(minutes: float) -> str:
    return f"{int(minutes // 60)} h {int(round(minutes % 60)):02d} m"


def _alert_view(a: dict) -> dict:
    steps = []
    for s in a.get("nextSteps") or []:
        if s.get("lockedForCMO"):
            steps.append("A further step is locked and needs CMO review (not shown to the assistant).")
        else:
            steps.append(s.get("text", ""))
    return {
        "id": a.get("id"), "ruleId": a.get("ruleId"), "level": a.get("level"), "ts": a.get("ts"),
        "status": a.get("status"), "title": a.get("title"), "whatChanged": a.get("whatChanged"),
        "missing": a.get("missing") or [], "possibleFactors": a.get("possibleFactors") or [],
        "nextSteps": steps, "sources": a.get("sources") or [],
    }


def build_context(perms: dict | None = None) -> dict[str, Any]:
    """The context dict given to the prompt. Only allowed, non-private fields."""
    perms = perms or get_permissions()
    allow = perms["assistant"]
    needed = {"alerts"}
    if allow["vitals"]:
        needed.add("latestReadings")
    if allow["sleep"]:
        needed.add("sleep")
    if allow["tests"]:
        needed.add("tests")
    if allow["exercise"]:
        needed |= {"exercisePlan", "todayPlan"}
    if allow["checkins"]:
        needed.add("checkins")
    raw, mocked = load_raw(needed)

    ctx: dict[str, Any] = {"simulated": True, "mockSources": sorted(mocked), "notShared": []}

    alerts = [a for a in (raw.get("alerts") or []) if a.get("status") != "closed"]
    alerts.sort(key=lambda a: a.get("ts") or "", reverse=True)
    ctx["alerts"] = [_alert_view(a) for a in alerts[:MAX_ALERTS]]

    if allow["vitals"]:
        vitals = []
        for lr in raw.get("latestReadings") or []:
            r = lr.get("reading") or {}
            if lr.get("quality") == "missing":
                # an old reading from a previous day must not look like today's value
                vitals.append({"metric": lr.get("metric"), "value": None, "quality": "missing",
                               "note": "no reading since the start of today's mission day"})
                continue
            vitals.append({"metric": lr.get("metric"), "value": r.get("value"), "unit": r.get("unit"),
                           "quality": lr.get("quality"), "age": _age(lr.get("ageMinutes"))})
        ctx["vitals"] = vitals
    else:
        ctx["notShared"].append("vitals")

    if allow["sleep"]:
        nights = _within_days(raw.get("sleep") or [], "end")
        if nights:
            durs = [n["durationMin"] for n in nights]
            short_h = threshold("sleep_short_hours")  # config/thresholds.yaml (needs its source filled in)
            ctx["sleep7d"] = {
                "nights": len(nights),
                "durationsMin": durs,
                "shortHours": short_h,
                "nightsUnderShort": sum(1 for d in durs if short_h is not None and d < short_h * 60),
                "average": _hm(sum(durs) / len(durs)),
                "shortest": _hm(min(durs)),
                "lastNight": _hm(nights[-1]["durationMin"]) if nights else None,
                "avgAwakenings": round(sum(n.get("awakenings") or 0 for n in nights) / len(nights), 1),
                "lastNights": [{"end": n["end"], "duration": _hm(n["durationMin"]),
                                "awakenings": n.get("awakenings"), "selfQuality": n.get("selfQuality")}
                               for n in nights[-3:]],
            }
        else:
            ctx["sleep7d"] = None
    else:
        ctx["notShared"].append("sleep")

    if allow["tests"]:
        tests = _within_days(raw.get("tests") or [], "ts")
        ctx["attention7d"] = [{"ts": t["ts"], "medianMs": t.get("medianMs"), "lapses": t.get("lapses"),
                               "falseStarts": t.get("falseStarts")} for t in tests]
    else:
        ctx["notShared"].append("attention tests")

    if allow["exercise"]:
        today = raw.get("todayPlan") or {}
        plan = next((p for p in (raw.get("exercisePlan") or []) if p.get("day") == today.get("missionDay")), None)
        ctx["exerciseToday"] = {
            "missionDay": today.get("missionDay"),
            "planned": f"{plan['type']} ({plan['durationMin']} min)" if plan else None,
            "logged": today.get("exerciseLogged"),
        }
    else:
        ctx["notShared"].append("exercise")

    if allow["checkins"]:
        # explicit allow-list of fields: notePrivate can never pass, whatever the source returns
        ctx["checkins7d"] = [{"ts": c.get("ts"), "mood": c.get("mood"), "stress": c.get("stress"),
                              "skipped": c.get("skipped")}
                             for c in _within_days(raw.get("checkins") or [], "ts")]
    else:
        ctx["notShared"].append("check-ins (permission off)")

    return ctx


def latest_alert(ctx: dict | None = None) -> dict | None:
    """The newest open alert, as the raw contract dict (for the template fallback)."""
    raw, _ = load_raw({"alerts"})
    alerts = [a for a in (raw.get("alerts") or []) if a.get("status") != "closed"] or (raw.get("alerts") or [])
    alerts.sort(key=lambda a: a.get("ts") or "", reverse=True)
    return alerts[0] if alerts else None
