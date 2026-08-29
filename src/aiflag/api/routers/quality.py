from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from aiflag.api.audit import utcnow
from aiflag.api.deps import require_admin
from aiflag.config import settings
from aiflag.db import get_db
from aiflag.engine.gates import ArmStats, percentile
from aiflag.models import AuditLog, Flag, GateDecision, GenerationEvent, QualityEvent
from aiflag.schemas import ArmQuality, AuditOut, GateDecisionOut, QualityOut

router = APIRouter(prefix="/api/v1", tags=["quality"])


def _arm(variant_key: str, gens: list[GenerationEvent], quals: list[QualityEvent]) -> ArmQuality:
    latencies = [float(g.latency_ms) for g in gens]
    errors = sum(1 for g in gens if g.error_code)
    tokens = [float((g.tokens_in or 0) + (g.tokens_out or 0)) for g in gens]
    judges = [q.score for q in quals if q.source == "judge"]
    samples = len(gens)
    return ArmQuality(
        variant_key=variant_key,
        samples=samples,
        error_rate=(errors / samples) if samples else 0.0,
        latency_p95=percentile(latencies, 95) if latencies else 0.0,
        judge_mean=(sum(judges) / len(judges)) if judges else 0.0,
        tokens_per_request=(sum(tokens) / samples) if samples else 0.0,
        judge_samples=len(judges),
    )


def collect_arm_stats(
    db: Session, flag_id, control_key: str, treatment_key: str | None, since
) -> tuple[ArmStats, ArmStats]:
    gens = (
        db.query(GenerationEvent)
        .filter(GenerationEvent.flag_id == flag_id, GenerationEvent.ts >= since)
        .all()
    )
    quals = (
        db.query(QualityEvent)
        .filter(QualityEvent.flag_id == flag_id, QualityEvent.ts >= since)
        .all()
    )
    by_var: dict[str, list[GenerationEvent]] = {}
    q_by_var: dict[str, list[QualityEvent]] = {}
    for g in gens:
        by_var.setdefault(g.variant_key, []).append(g)
    for q in quals:
        q_by_var.setdefault(q.variant_key, []).append(q)

    def to_stats(key: str) -> ArmStats:
        arm = _arm(key, by_var.get(key, []), q_by_var.get(key, []))
        return ArmStats(
            samples=arm.samples,
            error_rate=arm.error_rate,
            latency_p95=arm.latency_p95,
            judge_mean=arm.judge_mean,
            tokens_per_request=arm.tokens_per_request,
            judge_samples=arm.judge_samples,
        )

    treatment = to_stats(treatment_key) if treatment_key else ArmStats()
    return to_stats(control_key), treatment


@router.get("/flags/{flag_id}/quality", response_model=QualityOut)
def flag_quality(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> QualityOut:
    flag = (
        db.query(Flag)
        .options(joinedload(Flag.variants))
        .filter(Flag.id == flag_id)
        .first()
    )
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    control = next((v for v in flag.variants if v.is_control), None)
    treatment = next((v for v in flag.variants if not v.is_control), None)
    since = utcnow() - timedelta(minutes=settings.gate_window_minutes)
    gens = (
        db.query(GenerationEvent)
        .filter(GenerationEvent.flag_id == flag.id, GenerationEvent.ts >= since)
        .all()
    )
    quals = (
        db.query(QualityEvent)
        .filter(QualityEvent.flag_id == flag.id, QualityEvent.ts >= since)
        .all()
    )
    by_var: dict[str, list[GenerationEvent]] = {}
    q_by_var: dict[str, list[QualityEvent]] = {}
    for g in gens:
        by_var.setdefault(g.variant_key, []).append(g)
    for q in quals:
        q_by_var.setdefault(q.variant_key, []).append(q)

    last = (
        db.query(GateDecision)
        .filter(GateDecision.flag_id == flag.id)
        .order_by(GateDecision.ts.desc())
        .first()
    )
    return QualityOut(
        flag_key=flag.key,
        window_minutes=settings.gate_window_minutes,
        control=_arm(control.key, by_var.get(control.key, []), q_by_var.get(control.key, []))
        if control
        else None,
        treatment=_arm(treatment.key, by_var.get(treatment.key, []), q_by_var.get(treatment.key, []))
        if treatment
        else None,
        last_decision=GateDecisionOut(
            id=last.id,
            flag_id=last.flag_id,
            action=last.action,
            reason=last.reason,
            metrics=last.metrics or {},
            ts=last.ts,
        )
        if last
        else None,
    )


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
    limit: int = 100,
) -> list[AuditOut]:
    rows = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 500)).all()
    return [
        AuditOut(
            id=r.id,
            actor=r.actor,
            action=r.action,
            flag_id=r.flag_id,
            before=r.before,
            after=r.after,
            ts=r.ts,
        )
        for r in rows
    ]
