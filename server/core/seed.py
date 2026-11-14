"""Seeds the database with simulated data on first startup.

Run manually to wipe and regenerate:   python -m server.core.seed --reset
(or from the root:  npm run reseed)
"""
from __future__ import annotations

import sys
from datetime import datetime

from . import db
from .config import app_config, iso, parse_ts, utcnow
from .simulator import generate


def is_seeded() -> bool:
    return db.get_meta("seeded_at") is not None


def seed(now: datetime | None = None, *, force: bool = False) -> bool:
    """Generate and insert simulated data. Returns True if it seeded."""
    db.init_db()
    if is_seeded() and not force:
        return False
    if force:
        db.reset_db()
    now = now or utcnow()
    for table, rows in generate(now).items():
        db.insert_many(table, rows)
    db.set_meta("seeded_at", iso(now))
    db.set_meta("met_at_seed", app_config()["mission"]["met_at_seed"])
    return True


def seeded_at() -> datetime:
    """Anchor for the mission clock and comm schedule (falls back to now)."""
    v = db.get_meta("seeded_at")
    return parse_ts(v) if v else utcnow()


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    did = seed(force=reset)
    print("Seeded simulated data." if did else "Already seeded (use --reset to regenerate).")
    if did:
        from server.rules.engine import run_rules

        print(f"Rule engine created {len(run_rules())} alert(s).")
