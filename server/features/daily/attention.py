# Owner: Shahd
"""Attention (reaction-time) test endpoints."""
from __future__ import annotations

import statistics
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, threshold, utcnow
from server.core.models import ApiModel, CognitiveTest

router = APIRouter()


class TestIn(ApiModel):
    trials_ms: list[float] = Field(min_length=1)
    false_starts: int = 0
    ts: Optional[str] = None


@router.get("/tests")
def list_tests(n: int = Query(14, gt=0, le=100)) -> list[CognitiveTest]:
    rows = db.query("cognitive_tests", order_by="ts DESC", limit=n)
    return [CognitiveTest.model_validate(r) for r in reversed(rows)]


@router.post("/tests", status_code=201)
def add_test(body: TestIn) -> CognitiveTest:
    lapse_ms = float(threshold("pvt_lapse_ms"))
    t = CognitiveTest(
        id=db.new_id("pvt"), ts=body.ts or iso(utcnow()), trials_ms=body.trials_ms,
        median_ms=float(statistics.median(body.trials_ms)),
        lapses=sum(1 for x in body.trials_ms if x > lapse_ms), false_starts=body.false_starts,
    )
    db.insert("cognitive_tests", t.model_dump())
    db.log_action("crew", "attention_test", t.id)
    return t
