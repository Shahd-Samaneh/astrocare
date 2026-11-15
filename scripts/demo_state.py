"""Pre-demo data check: is the database in the demo's starting state? One line per check, ✅ or ❌.

    npm run reseed                                   # first: fresh demo data
    node scripts/py.mjs scripts/demo_state.py        (any OS, uses the project's .venv)

Checks (read-only: it calls the API in-process, without the app's startup hooks, so nothing is
written and Ollama is not needed). Run scripts/demo_check.py too for the assistant/Ollama side.
  1. mission day is 142
  2. R-FAT-01 is open at review, with "Today's check-in" in missing
  3. skin temperature is stale
  4. blood pressure is missing
  5. the outbox is empty (no queued reports, no pending report items)
  6. assistant permissions are at their defaults
  7. the Relax media files are present and served
  8. heart rate, SpO2 and respiration are still fresh (they go stale 2 h after a reseed)
  9. cabin CO2 / temperature / noise / humidity are fresh (same stale rule as the vitals)
 10. vision self-check: the 2 seeded checks (days 130, 137), "Same as baseline", no R-VIS-01
 11. the live feed is running (needs the server: npm run start / npm run dev), see
     server/core/live_feed.py

Exit code 0 when every check passed, 1 otherwise.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASTROCARE_NO_WARMUP", "1")

MEDIA_FILES = [
    "scenes/earthrise.png", "scenes/ocean-shore.png", "scenes/forest-stream.png",
    "audio/ocean-shore-nature.wav", "audio/rain-window-nature.wav", "audio/forest-stream-nature.wav",
    "audio/music-ambient-pad.wav",
]


def run_state_checks(log: Callable[[str], None] = print) -> list[tuple[str, bool, str]]:
    from fastapi.testclient import TestClient

    from server.features.assistant.permissions import DEFAULT_PERMISSIONS
    from server.main import app

    c = TestClient(app)  # not used as a context manager: no startup hooks (no seeding, no rule run)
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn: Callable[[], tuple[bool, str]]) -> None:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001  any failure is a ❌, never a crash
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, detail))
        log(f"{'✅' if ok else '❌'} {name:<42} {detail}")

    def get(path: str) -> Any:
        r = c.get(path)
        r.raise_for_status()
        return r.json()

    def latest() -> dict[str, dict]:
        return {x["metric"]: x for x in get("/api/readings/latest")}

    def mission_day() -> tuple[bool, str]:
        day = get("/api/status")["missionDay"]
        return day == 142, f"day {day}"

    def fatigue() -> tuple[bool, str]:
        open_ = [a for a in get("/api/alerts") if a["ruleId"] == "R-FAT-01" and a["status"] != "closed"]
        if not open_:
            return False, "no open R-FAT-01 alert (run npm run reseed)"
        a = open_[0]
        ok = a["level"] == "review" and a["status"] in ("new", "ack") and "Today's check-in" in a["missing"]
        return ok, f"level {a['level']}, status {a['status']}, missing {a['missing']}"

    def skin_stale() -> tuple[bool, str]:
        q = latest().get("skin_temp", {}).get("quality")
        return q == "stale", f"skin_temp {q}"

    def bp_missing() -> tuple[bool, str]:
        lt = latest()
        qs = {m: lt.get(m, {}).get("quality", "missing") for m in ("bp_sys", "bp_dia")}
        return all(q == "missing" for q in qs.values()), ", ".join(f"{m} {q}" for m, q in qs.items())

    def outbox() -> tuple[bool, str]:
        queued = get("/api/status")["outboxCount"]
        items = len(get("/api/reports/items?pending=true"))
        return queued == 0 and items == 0, f"{queued} queued report(s), {items} pending item(s)"

    def permissions() -> tuple[bool, str]:
        p = get("/api/assistant/permissions")
        if p == DEFAULT_PERMISSIONS:
            return True, "defaults (check-ins off)"
        return False, f"changed: {p}"

    def media() -> tuple[bool, str]:
        lost = [f for f in MEDIA_FILES if c.get(f"/api/relax/media/{f}").status_code != 200]
        if lost:
            return False, "missing: " + ", ".join(lost) + "  (run: python scripts/make_relax_media.py)"
        return True, f"{len(MEDIA_FILES)} files served"

    def fresh_vitals() -> tuple[bool, str]:
        lt = latest()
        qs = {m: lt.get(m, {}).get("quality", "missing") for m in ("heart_rate", "spo2", "resp_rate")}
        ok = all(q in ("good", "low") for q in qs.values())
        return ok, ", ".join(f"{m} {q}" for m, q in qs.items()) + ("" if ok else "  (reseed: data is > 2 h old)")

    def fresh_cabin() -> tuple[bool, str]:
        entries = get("/api/cabin/latest")
        bad = [e for e in entries if e["status"] == "missing" or e.get("stale")]
        detail = ", ".join(
            f"{e['metric']} {'missing' if e['status'] == 'missing' else ('stale' if e.get('stale') else 'fresh')}"
            + (f" ({e['ageMinutes']} min)" if e.get("ageMinutes") is not None else "")
            for e in entries
        )
        return not bad, detail + ("" if not bad else "  (start the server for the live feed, or reseed)")

    check("Mission day 142", mission_day)
    check("R-FAT-01 open at review, check-in missing", fatigue)
    check("Skin temperature stale", skin_stale)
    check("Blood pressure missing", bp_missing)
    check("Outbox empty", outbox)
    check("Assistant permissions at defaults", permissions)
    check("Relax media present", media)
    def feed() -> tuple[bool, str]:
        from server.core import db, live_feed
        from server.core.config import parse_ts, utcnow
        if not live_feed.settings()["enabled"]:
            return False, "off: set simulator.live_feed.enabled: true in config/app.yaml"
        beat = db.get_meta(live_feed.HEARTBEAT_KEY)
        if not beat:
            return False, "no heartbeat: start the server (npm run start / npm run dev); it ticks every minute"
        age_s = (utcnow() - parse_ts(beat)).total_seconds()
        if age_s > 180:
            return False, f"last tick {age_s / 60:.0f} min ago: is the server running?"
        def ago(table: str) -> str:
            live = db.query(table, "id LIKE 'live-%'", order_by="ts DESC", limit=1)
            return f"{(utcnow() - parse_ts(live[0]['ts'])).total_seconds() / 60:.0f} min ago" if live else "none yet"
        cfg = live_feed.settings()
        return True, (f"tick {age_s:.0f} s ago; vitals every {cfg['every_minutes']:g} min (last {ago('readings')}), "
                      f"cabin every {cfg['cabin_every_minutes']:g} min (last {ago('cabin_readings')})")

    check("HR / SpO2 / resp still fresh", fresh_vitals)
    check("Cabin readings fresh", fresh_cabin)

    def vision() -> tuple[bool, str]:
        checks = get("/api/vision/checks?n=10")
        s = get("/api/vision/summary")
        vis_alerts = [a for a in get("/api/alerts") if a["ruleId"] == "R-VIS-01" and a["status"] != "closed"]
        ids = sorted(ch["id"] for ch in checks)
        ok = ids == ["vis-130", "vis-137"] and s["status"] == "stable" and not vis_alerts
        return ok, f"{len(checks)} check(s) {ids}, {s['result']}, {len(vis_alerts)} open R-VIS-01" + (
            "" if ok else "  (run npm run reseed)")

    check("Vision self-check seeded, no change", vision)
    check("Live feed running", feed)
    return results


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles: print ✅ / ❌ instead of crashing
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    print("Demo state check (run `npm run reseed` first; this script only reads).\n")
    results = run_state_checks()
    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"❌ {len(failed)} of {len(results)} checks failed: " + ", ".join(failed))
        return 1
    print(f"✅ All {len(results)} checks passed. Demo data is in its starting state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
