from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from aiflag.api.audit import utcnow
from aiflag.api.deps import require_admin
from aiflag.config import settings
from aiflag.db import get_db
from aiflag.engine import evaluate, snapshot_from_orm
from aiflag.models import AuditLog, Flag, GateDecision, GenerationEvent, Impression, QualityEvent
from aiflag.schemas import EvaluateIn, EvaluateOut
from datetime import timedelta
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["system"])


class SystemStatus(BaseModel):
    status: str
    database: str
    ollama: str
    demo_mock_llm: bool
    gate_enabled: bool
    gate_window_minutes: int
    flag_count: int
    active_flags: int
    impressions_15m: int
    generations_15m: int
    quality_events_15m: int
    last_gate_action: str | None = None
    last_gate_reason: str | None = None


@router.get("/system/status", response_model=SystemStatus)
def system_status(
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> SystemStatus:
    db_ok = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"

    ollama = "unchecked"
    if not settings.demo_mock_llm:
        try:
            from urllib.parse import urlparse
            import socket

            parsed = urlparse(settings.ollama_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            with socket.create_connection((host, port), timeout=0.4):
                pass
            with httpx.Client(timeout=httpx.Timeout(1.0, connect=0.4)) as client:
                r = client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
                ollama = "ok" if r.status_code == 200 else f"http_{r.status_code}"
        except Exception:
            ollama = "down"
    else:
        ollama = "mock"

    since = utcnow() - timedelta(minutes=settings.gate_window_minutes)
    flag_count = db.query(func.count(Flag.id)).filter(Flag.archived.is_(False)).scalar() or 0
    active = (
        db.query(func.count(Flag.id))
        .filter(Flag.archived.is_(False), Flag.status == "active")
        .scalar()
        or 0
    )
    impressions = db.query(func.count(Impression.id)).filter(Impression.ts >= since).scalar() or 0
    generations = (
        db.query(func.count(GenerationEvent.id)).filter(GenerationEvent.ts >= since).scalar() or 0
    )
    quality = db.query(func.count(QualityEvent.id)).filter(QualityEvent.ts >= since).scalar() or 0
    last = db.query(GateDecision).order_by(GateDecision.ts.desc()).first()

    return SystemStatus(
        status="ok" if db_ok == "ok" else "degraded",
        database=db_ok,
        ollama=ollama,
        demo_mock_llm=settings.demo_mock_llm,
        gate_enabled=settings.gate_enabled,
        gate_window_minutes=settings.gate_window_minutes,
        flag_count=int(flag_count),
        active_flags=int(active),
        impressions_15m=int(impressions),
        generations_15m=int(generations),
        quality_events_15m=int(quality),
        last_gate_action=last.action if last else None,
        last_gate_reason=last.reason if last else None,
    )


@router.post("/evaluate", response_model=EvaluateOut)
def admin_evaluate(
    body: EvaluateIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> EvaluateOut:
    flag = (
        db.query(Flag)
        .options(joinedload(Flag.variants), joinedload(Flag.rules), joinedload(Flag.rollout))
        .filter(Flag.key == body.flag_key, Flag.archived.is_(False))
        .first()
    )
    snap = snapshot_from_orm(flag) if flag else None
    result = evaluate(snap, body.user_key, body.attributes)
    if flag is not None:
        db.add(
            Impression(
                flag_id=flag.id,
                user_key=body.user_key,
                variant_key=result.variant_key,
                reason=result.reason,
            )
        )
        db.commit()
    return EvaluateOut(
        flag_key=result.flag_key,
        variant_key=result.variant_key,
        payload=result.payload,
        reason=result.reason,
        bucket=result.bucket,
    )


@router.get("/gate-decisions")
def list_gate_decisions(
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = db.query(GateDecision).order_by(GateDecision.ts.desc()).limit(min(limit, 200)).all()
    flag_ids = {r.flag_id for r in rows}
    keys = {
        f.id: f.key for f in db.query(Flag).filter(Flag.id.in_(flag_ids)).all()
    } if flag_ids else {}
    return [
        {
            "id": str(r.id),
            "flag_id": str(r.flag_id),
            "flag_key": keys.get(r.flag_id, ""),
            "action": r.action,
            "reason": r.reason,
            "metrics": r.metrics or {},
            "ts": r.ts.isoformat() if r.ts else None,
        }
        for r in rows
    ]


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    flags = (
        db.query(Flag)
        .options(joinedload(Flag.rollout), joinedload(Flag.variants))
        .filter(Flag.archived.is_(False))
        .order_by(Flag.key)
        .all()
    )
    recent = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(8).all()
    return {
        "flags": [
            {
                "id": str(f.id),
                "key": f.key,
                "name": f.name,
                "status": f.status,
                "kill_switch": f.kill_switch,
                "percentage_bps": f.rollout.percentage_bps if f.rollout else 0,
                "auto_advance": f.rollout.auto_advance if f.rollout else False,
                "variant_count": len(f.variants),
            }
            for f in flags
        ],
        "recent_audit": [
            {
                "id": str(a.id),
                "actor": a.actor,
                "action": a.action,
                "ts": a.ts.isoformat() if a.ts else None,
                "after": a.after,
            }
            for a in recent
        ],
    }
