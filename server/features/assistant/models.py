"""Local copies of the assistant's contract types (proposal A1–A3 in
docs/proposals/support-contracts.md). Switch to server.core.models once Haya merges them.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from server.core.models import ApiModel

RefusalReason = Literal["medication", "diagnosis"]
AnswerMode = Literal["llm", "fallback"]


class AskIn(ApiModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantSource(ApiModel):
    id: str
    title: str
    url: Optional[str] = None


class AssistantAnswer(ApiModel):
    answer: str
    sources: list[AssistantSource] = []
    missing: list[str] = []
    refused: bool = False
    refusal_reason: Optional[RefusalReason] = None
    mode: AnswerMode
    latency_ms: int


class AssistantPermissionsGroup(ApiModel):
    vitals: bool = True
    sleep: bool = True
    tests: bool = True
    exercise: bool = True
    checkins: bool = False


class ReportPermissionsGroup(ApiModel):
    checkins: bool = False


class AssistantPermissions(ApiModel):
    assistant: AssistantPermissionsGroup
    report: ReportPermissionsGroup


class PermissionsPatch(ApiModel):
    """PUT body: any subset, e.g. {"assistant": {"checkins": true}}."""

    assistant: Optional[dict[str, bool]] = None
    report: Optional[dict[str, bool]] = None


class AssistantInfo(ApiModel):
    ollama_url: str
    reachable: bool
    chat_model: str
    embed_model: str
    models_available: list[str] = []
    model_size_bytes: Optional[int] = None
    ram_bytes: Optional[int] = None
    avg_latency_ms: Optional[float] = None
    tokens_per_sec: Optional[float] = None
    answers_logged: int = 0
    chunks_indexed: int = 0
