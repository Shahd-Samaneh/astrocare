"""Daily test helpers (owner: Shahd): a fresh, seeded DB per test.

`daily_client()` points ASTROCARE_DB_PATH at a new temp file, seeds the demo
scenario, optionally removes today's check-in (emulating the simulator change we
asked Haya for in docs/proposals/daily-contracts.md §4), runs the engine, and
yields a TestClient. The previous DB path is restored afterwards, so the shared
session `client` fixture is unaffected.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient


@contextmanager
def daily_client(*, remove_today_checkin: bool = True) -> Iterator[TestClient]:
    from server.core import db
    from server.core.config import iso
    from server.core.seed import seed
    from server.core.status import mission_day_start
    from server.features.daily.engine_hooks import run_daily_engine
    from server.main import app

    old = os.environ.get("ASTROCARE_DB_PATH")
    os.environ["ASTROCARE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="astrocare-daily-")) / "daily.db")
    try:
        seed(force=True)
        if remove_today_checkin:
            with db.connect() as conn:
                conn.execute("DELETE FROM checkins WHERE ts >= ?", (iso(mission_day_start()),))
        with TestClient(app) as c:  # lifespan: already seeded, runs the engine
            run_daily_engine()
            yield c
    finally:
        if old is None:
            os.environ.pop("ASTROCARE_DB_PATH", None)
        else:
            os.environ["ASTROCARE_DB_PATH"] = old


def open_alert(c: TestClient, rule_id: str) -> dict:
    alerts = [a for a in c.get("/api/alerts").json() if a["ruleId"] == rule_id and a["status"] != "closed"]
    assert len(alerts) == 1, f"expected exactly one open {rule_id} alert, got {len(alerts)}"
    return alerts[0]
