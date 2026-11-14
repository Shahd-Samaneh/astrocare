"""Source of truth for the data contract. Change both files together, via Haya.

Mirror of app/src/shared/types/contracts.ts.

Python fields are snake_case (they match the SQLite column names); JSON uses
camelCase through the alias generator, so the API speaks exactly the TS contract.
Request bodies accept either spelling.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# ---- Enums ---------------------------------------------------------------
Quality = Literal["good", "low", "stale", "missing"]
Source = Literal["dataset", "simulated", "manual", "sensor"]
Metric = Literal["heart_rate", "spo2", "skin_temp", "bp_sys", "bp_dia", "resp_rate"]
CabinMetric = Literal["co2", "cabin_temp", "noise", "humidity"]
SensorStatus = Literal["connected", "disconnected", "low_battery"]
ExerciseStatus = Literal["done", "partial", "skipped"]
ExerciseReason = Literal["pain", "fatigue", "equipment", "time"]
ResourceKind = Literal["medicine", "equipment"]
ResourceStatus = Literal["available", "low", "out_of_stock", "expired"]
AlertLevel = Literal["info", "review", "urgent"]
AlertStatus = Literal["new", "ack", "recheck", "closed"]
Availability = Literal["available", "out_of_stock", "expired", "allergy_conflict"]
AudioMode = Literal["nature", "music", "none"]
ReportStatus = Literal["draft", "ready", "queued", "sent"]

METRICS: tuple[str, ...] = ("heart_rate", "spo2", "skin_temp", "bp_sys", "bp_dia", "resp_rate")
CABIN_METRICS: tuple[str, ...] = ("co2", "cabin_temp", "noise", "humidity")


class ApiModel(BaseModel):
    """Base for every contract model: camelCase JSON, snake_case Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ---- Contract ------------------------------------------------------------
class Reading(ApiModel):
    id: str
    astronaut_id: str
    metric: Metric
    value: float
    unit: str
    ts: str
    source: Source
    quality: Quality


class CabinReading(ApiModel):
    id: str
    metric: CabinMetric
    value: float
    unit: str
    ts: str
    source: Source


class Sensor(ApiModel):
    id: str
    name: str
    location: str
    metrics: list[str]
    status: SensorStatus
    last_seen: str


class Baseline(ApiModel):
    mean: float
    sd: float
    n: int


class Profile(ApiModel):
    id: str
    name: str
    mission_day: int
    allergies: list[str]
    current_meds: list[str]
    history: list[str]
    # Keys: any Metric plus 'pvt_median_ms' and 'sleep_hours'.
    baseline: dict[str, Baseline]


class SleepSession(ApiModel):
    id: str
    start: str
    end: str
    duration_min: int
    awakenings: int
    self_quality: Optional[int] = Field(default=None, ge=1, le=5)
    source: Source


class CognitiveTest(ApiModel):
    id: str
    ts: str
    trials_ms: list[float]
    median_ms: float
    lapses: int
    false_starts: int


class CheckIn(ApiModel):
    id: str
    ts: str
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    stress: Optional[int] = Field(default=None, ge=1, le=5)
    note_private: Optional[str] = None
    skipped: bool = False


class ExerciseAlternative(ApiModel):
    id: str
    type: str
    duration_min: int
    equipment_id: Optional[str] = None
    note: Optional[str] = None


class ExercisePlan(ApiModel):
    id: str
    day: int  # mission day
    type: str
    duration_min: int
    equipment_id: Optional[str] = None
    alternatives: list[ExerciseAlternative] = []


class ExerciseLog(ApiModel):
    id: str
    plan_id: str
    ts: str
    status: ExerciseStatus
    reason: Optional[ExerciseReason] = None
    alternative_id: Optional[str] = None


class Resource(ApiModel):
    id: str
    kind: ResourceKind
    name: str
    qty: float
    unit: str
    expiry: Optional[str] = None
    status: ResourceStatus
    contraindicated_allergies: list[str] = []


class NextStep(ApiModel):
    text: str
    resource_id: Optional[str] = None
    availability: Optional[Availability] = None
    locked_for_cmo: bool = Field(default=False, alias="lockedForCMO")


class Alert(ApiModel):
    id: str
    rule_id: str
    level: AlertLevel
    ts: str
    title: str
    what_changed: str
    data_used: list[str] = []  # reading ids
    missing: list[str] = []
    possible_factors: list[str] = []
    next_steps: list[NextStep] = []
    status: AlertStatus = "new"
    sources: list[str] = []


class RelaxSession(ApiModel):
    id: str
    ts: str
    scene_id: str
    audio_mode: AudioMode
    duration_min: int
    stress_before: int = Field(ge=1, le=5)
    stress_after: Optional[int] = Field(default=None, ge=1, le=5)


class ReportSection(ApiModel):
    id: str
    title: str
    body: str = ""


class Report(ApiModel):
    id: str
    created_ts: str
    status: ReportStatus
    sections: list[ReportSection] = []
    file_path: Optional[str] = None


class ActionLog(ApiModel):
    id: str
    ts: str
    actor: str
    action: str
    ref_id: Optional[str] = None


class AppStatus(ApiModel):
    mission_name: str
    mission_day: int
    met: str  # "DDD:HH:MM", e.g. "142:07:31"
    local_mode: bool
    next_comm_window_ts: str
    signal_delay_sec: int
    last_sync_ts: str
    outbox_count: int
    simulated: bool
    crew_name: str
    crew_initials: str
