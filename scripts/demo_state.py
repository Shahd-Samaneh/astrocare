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

    check("Mission day 142", mission_day)
    check("R-FAT-01 open at review, check-in missing", fatigue)
    check("Skin temperature stale", skin_stale)
    check("Blood pressure missing", bp_missing)
    check("Outbox empty", outbox)
    check("Assistant permissions at defaults", permissions)
    check("Relax media present", media)
    check("HR / SpO2 / resp still fresh", fresh_vitals)
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
