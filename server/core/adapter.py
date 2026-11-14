"""Dataset adapter: maps the hackathon dataset onto the AstroCare data contract.

Not implemented yet: we only get the dataset at the hackathon. Until then the
app runs on simulated data (core/simulator.py).
"""
from __future__ import annotations

from pathlib import Path


def load_dataset(path: str | Path) -> dict[str, list]:
    """Load the hackathon dataset found at `path` (a file or folder in data/raw/).

    Returns a dict keyed by DB table name, each value a list of rows (plain dicts)
    whose keys are the snake_case fields of the matching model in core/models.py:

        {
          "readings":        [ {id, astronaut_id, metric, value, unit, ts, source="dataset", quality}, ... ],
          "cabin_readings":  [ {id, metric, value, unit, ts, source="dataset"}, ... ],
          "sleep_sessions":  [ {id, start, end, duration_min, awakenings, self_quality, source="dataset"}, ... ],
          "cognitive_tests": [ {id, ts, trials_ms, median_ms, lapses, false_starts}, ... ],
          "checkins":        [ ... ],
          "sensors":         [ ... ],
          "profiles":        [ ... ],
        }

    Rules for the mapping:
      * every row coming from the dataset sets ``source = "dataset"``;
      * timestamps are ISO 8601 UTC strings ending in "Z" (use core.config.iso);
      * metric names and units must be the ones listed in core/models.py
        (convert units here, e.g. °F -> °C);
      * unknown or unusable columns are dropped, never guessed;
      * tables the dataset doesn't cover are simply left out of the dict
        (the simulator keeps filling them, and those rows stay "simulated").

    The result can be written with ``db.insert_many(table, rows)`` for each item.
    """
    # TODO(monitoring pair + Haya): implement once the dataset format is known.
    return {}
