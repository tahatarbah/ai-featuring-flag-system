from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from aiflag.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class FlagStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    killed = "killed"


class FlagType(str, enum.Enum):
    boolean = "boolean"
    multivariate = "multivariate"


class GateAction(str, enum.Enum):
    pause = "pause"
    rollback = "rollback"
    advance = "advance"
    pass_ = "pass"
    skip = "skip"


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    flag_type: Mapped[str] = mapped_column(String(32), default=FlagType.multivariate.value)
    status: Mapped[str] = mapped_column(String(32), default=FlagStatus.draft.value, index=True)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    salt: Mapped[str] = mapped_column(String(64), default=lambda: uuid.uuid4().hex)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    variants: Mapped[list[FlagVariant]] = relationship(
        back_populates="flag", cascade="all, delete-orphan", order_by="FlagVariant.created_at"
    )
    rules: Mapped[list[TargetingRule]] = relationship(
        back_populates="flag", cascade="all, delete-orphan", order_by="TargetingRule.priority"
    )
    rollout: Mapped[Rollout | None] = relationship(
        back_populates="flag", cascade="all, delete-orphan", uselist=False
    )
    slos: Mapped[list[QualitySLO]] = relationship(
        back_populates="flag", cascade="all, delete-orphan"
    )


class FlagVariant(Base):
    __tablename__ = "flag_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    flag: Mapped[Flag] = relationship(back_populates="variants")


class TargetingRule(Base):
    __tablename__ = "targeting_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attribute: Mapped[str] = mapped_column(String(64))
    op: Mapped[str] = mapped_column(String(16))  # eq | in | contains
    value: Mapped[str] = mapped_column(Text)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flag_variants.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    flag: Mapped[Flag] = relationship(back_populates="rules")
    variant: Mapped[FlagVariant] = relationship()


class Rollout(Base):
    __tablename__ = "rollouts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flags.id", ondelete="CASCADE"), unique=True, index=True
    )
    percentage_bps: Mapped[int] = mapped_column(Integer, default=0)  # 0–10000
    stage: Mapped[int] = mapped_column(Integer, default=0)
    auto_advance: Mapped[bool] = mapped_column(Boolean, default=False)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    flag: Mapped[Flag] = relationship(back_populates="rollout")


class QualitySLO(Base):
    __tablename__ = "quality_slos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(64))
    comparator: Mapped[str] = mapped_column(String(32), default="max_delta")
    threshold: Mapped[float] = mapped_column(Float)
    min_samples: Mapped[int] = mapped_column(Integer, default=20)
    action: Mapped[str] = mapped_column(String(16), default=GateAction.pause.value)

    flag: Mapped[Flag] = relationship(back_populates="slos")


class SdkKey(Base):
    __tablename__ = "sdk_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Impression(Base):
    __tablename__ = "impressions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    user_key: Mapped[str] = mapped_column(String(255), index=True)
    variant_key: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class GenerationEvent(Base):
    __tablename__ = "generation_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    user_key: Mapped[str] = mapped_column(String(255), index=True)
    variant_key: Mapped[str] = mapped_column(String(64), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class QualityEvent(Base):
    __tablename__ = "quality_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    user_key: Mapped[str] = mapped_column(String(255), index=True)
    variant_key: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))  # judge | thumbs
    comment: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("flags.id", ondelete="SET NULL"), nullable=True, index=True
    )
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class GateDecision(Base):
    __tablename__ = "gate_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
