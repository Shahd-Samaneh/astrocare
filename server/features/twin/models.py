"""Response models for GET /api/twin/state and GET /api/twin/timeline (owner: Shahd).

These are twin-only view models (not part of the shared contract in core/models.py).
JSON is camelCase like every other endpoint.
"""
from __future__ import annotations

from typing import Literal, Optional, Union

from server.core.models import ApiModel, SensorStatus

TwinStatus = Literal["ok", "watch", "review", "urgent", "nodata"]
RegionId = Literal["brain", "eyes", "heart", "lungs", "bones", "radiation", "temperature", "sensors"]
REGION_IDS: tuple[str, ...] = ("brain", "eyes", "heart", "lungs", "bones", "radiation", "temperature", "sensors")

# Shown on every estimate value (radiation), everywhere, including the timeline.
ESTIMATE_LABEL = "Estimate · simulated"
NO_DATA = "No data"
DISCLAIMER = "Visual summary. Not a medical device."


class TwinValue(ApiModel):
    """One line on the region card. value None = "No data" (never an invented number).

    quality: a reading quality ('good' | 'low' | 'stale' | 'missing') or a label for a value that is
    not a measurement ('estimate', 'illustrative', 'self-check').
    """

    label: str
    value: Optional[Union[float, str]] = None
    unit: Optional[str] = None
    quality: Optional[str] = None


class TwinAlertRef(ApiModel):
    id: str
    rule_id: str
    title: str
    level: str


class TwinSource(ApiModel):
    id: str
    title: str


class TwinSensor(ApiModel):
    """An on-body or kit sensor from GET /sensors. anchor = where the 3D marker goes;
    None = not worn on the body (e.g. the blood pressure cuff in the medical kit): panel only."""

    id: str
    name: str
    location: str
    status: SensorStatus
    last_seen: str
    anchor: Optional[Literal["chest", "upperArm", "leftWrist"]] = None


class TwinRegion(ApiModel):
    id: RegionId
    label: str
    status: TwinStatus
    headline: str
    values: list[TwinValue] = []
    alerts: list[str] = []  # rule ids of the related open alerts
    alert_refs: list[TwinAlertRef] = []  # same alerts with their id (for links) and title
    route: str
    route_label: str
    sources: list[str] = []  # reference ids (references/<id>.txt)
    source_titles: list[TwinSource] = []
    estimate: bool = False  # the main value is an estimate, not a measurement (radiation)
    pulse_bpm: Optional[float] = None  # heart only: the beat rate for the 3D pulse (None = no pulse)
    sensors: Optional[list[TwinSensor]] = None  # sensors region only


class TwinState(ApiModel):
    mission_day: int
    simulated: bool
    generated_at: str
    disclaimer: str = DISCLAIMER
    regions: list[TwinRegion]


class TwinDay(ApiModel):
    mission_day: int
    is_today: bool
    as_of: str  # end of that mission day (or now, for today)
    regions: list[TwinRegion]


class TwinTimeline(ApiModel):
    from_day: int
    to_day: int
    today: int
    simulated: bool
    disclaimer: str = DISCLAIMER
    days: list[TwinDay]
