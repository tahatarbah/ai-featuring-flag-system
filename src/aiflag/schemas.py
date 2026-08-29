from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class VariantIn(BaseModel):
    key: str
    is_control: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class VariantOut(VariantIn):
    id: uuid.UUID


class RuleIn(BaseModel):
    priority: int = 0
    attribute: str
    op: str
    value: str
    variant_key: str


class RuleOut(BaseModel):
    id: uuid.UUID
    priority: int
    attribute: str
    op: str
    value: str
    variant_id: uuid.UUID
    variant_key: str


class RolloutOut(BaseModel):
    percentage_bps: int
    stage: int
    auto_advance: bool
    last_action_at: datetime | None = None


class SLOIn(BaseModel):
    metric: str
    comparator: str = "max_delta"
    threshold: float
    min_samples: int = 20
    action: str = "pause"


class SLOOut(SLOIn):
    id: uuid.UUID


class FlagCreate(BaseModel):
    key: str
    name: str
    description: str = ""
    flag_type: str = "multivariate"
    variants: list[VariantIn]
    rules: list[RuleIn] = Field(default_factory=list)
    percentage_bps: int = 0
    auto_advance: bool = False
    slos: list[SLOIn] = Field(default_factory=list)


class FlagUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    kill_switch: bool | None = None
    auto_advance: bool | None = None
    percentage_bps: int | None = None
    salt: str | None = None


class FlagOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str
    flag_type: str
    status: str
    kill_switch: bool
    salt: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    variants: list[VariantOut]
    rules: list[RuleOut]
    rollout: RolloutOut | None
    slos: list[SLOOut]


class EvaluateIn(BaseModel):
    flag_key: str
    user_key: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class EvaluateOut(BaseModel):
    flag_key: str
    variant_key: str
    payload: dict[str, Any]
    reason: str
    bucket: int | None = None


class ImpressionIn(BaseModel):
    flag_key: str
    user_key: str
    variant_key: str
    reason: str


class GenerationIn(BaseModel):
    flag_key: str
    user_key: str
    variant_key: str
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error_code: str | None = None
    model: str = ""


class QualityIn(BaseModel):
    flag_key: str
    user_key: str
    variant_key: str
    score: float
    source: str = "thumbs"
    comment: str = ""


class EventsIn(BaseModel):
    impressions: list[ImpressionIn] = Field(default_factory=list)
    generations: list[GenerationIn] = Field(default_factory=list)
    quality: list[QualityIn] = Field(default_factory=list)


class AskIn(BaseModel):
    user_key: str
    question: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class AskOut(BaseModel):
    answer: str
    evaluation: EvaluateOut
    confidence_shown: bool = False
    judge_score: float | None = None
    judge_reason: str = ""
    latency_ms: int
    tokens_in: int
    tokens_out: int
    error_code: str | None = None
    model: str = ""


class ThumbsIn(BaseModel):
    user_key: str
    flag_key: str = "support_assistant"
    variant_key: str
    score: float
    comment: str = ""


class AuditOut(BaseModel):
    id: uuid.UUID
    actor: str
    action: str
    flag_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ts: datetime


class GateDecisionOut(BaseModel):
    id: uuid.UUID
    flag_id: uuid.UUID
    action: str
    reason: str
    metrics: dict[str, Any]
    ts: datetime


class ArmQuality(BaseModel):
    variant_key: str
    samples: int
    error_rate: float
    latency_p95: float
    judge_mean: float
    tokens_per_request: float
    judge_samples: int


class QualityOut(BaseModel):
    flag_key: str
    window_minutes: int
    control: ArmQuality | None
    treatment: ArmQuality | None
    last_decision: GateDecisionOut | None
