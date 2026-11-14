"""Test setup: put the project root on sys.path and use a throwaway database."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="astrocare-test-")
os.environ["ASTROCARE_DB_PATH"] = str(Path(_tmp) / "test.db")


def pytest_configure(config):
    # Third-party notice from Starlette's TestClient; not actionable for us.
    config.addinivalue_line("filterwarnings", "ignore:Using `httpx` with `starlette.testclient`")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as c:  # runs the lifespan: init DB, seed, run rules
        yield c
