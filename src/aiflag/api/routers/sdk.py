from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from aiflag.api.deps import require_sdk
from aiflag.db import get_db
from aiflag.engine import evaluate, snapshot_from_orm
from aiflag.models import (
    Flag,
    GenerationEvent,
    Impression,
    QualityEvent,
    SdkKey,
)
from aiflag.schemas import EvaluateIn, EvaluateOut, EventsIn

router = APIRouter(prefix="/sdk/v1", tags=["sdk"])

_FLAG_LOAD = (
    joinedload(Flag.variants),
    joinedload(Flag.rules),
    joinedload(Flag.rollout),
)


def _config_payload(flags: list[Flag]) -> dict[str, Any]:
    out: dict[str, Any] = {"flags": {}}
    for flag in flags:
        snap = snapshot_from_orm(flag)
        out["flags"][flag.key] = {
            "key": snap.key,
            "flag_type": snap.flag_type,
            "status": snap.status,
            "kill_switch": snap.kill_switch,
            "salt": snap.salt,
            "archived": snap.archived,
            "percentage_bps": snap.percentage_bps,
            "variants": [
                {"key": v.key, "is_control": v.is_control, "payload": v.payload} for v in snap.variants
            ],
            "rules": [
                {
                    "priority": r.priority,
                    "attribute": r.attribute,
                    "op": r.op,
                    "value": r.value,
                    "variant_key": r.variant_key,
                }
                for r in snap.rules
            ],
        }
    return out


@router.get("/config")
def get_config(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SdkKey, Depends(require_sdk)],
) -> dict[str, Any]:
    flags = db.query(Flag).options(*_FLAG_LOAD).filter(Flag.archived.is_(False)).all()
    return _config_payload(flags)


@router.post("/evaluate", response_model=EvaluateOut)
def evaluate_remote(
    body: EvaluateIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SdkKey, Depends(require_sdk)],
) -> EvaluateOut:
    flag = (
        db.query(Flag)
        .options(*_FLAG_LOAD)
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


@router.post("/events")
def ingest_events(
    body: EventsIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[SdkKey, Depends(require_sdk)],
) -> dict[str, int]:
    keys = {e.flag_key for e in body.impressions + body.generations + body.quality}
    flags = {f.key: f for f in db.query(Flag).filter(Flag.key.in_(keys)).all()} if keys else {}

    accepted = 0
    for event in body.impressions:
        flag = flags.get(event.flag_key)
        if flag is None:
            continue
        db.add(
            Impression(
                flag_id=flag.id,
                user_key=event.user_key,
                variant_key=event.variant_key,
                reason=event.reason,
            )
        )
        accepted += 1
    for event in body.generations:
        flag = flags.get(event.flag_key)
        if flag is None:
            continue
        db.add(
            GenerationEvent(
                flag_id=flag.id,
                user_key=event.user_key,
                variant_key=event.variant_key,
                latency_ms=event.latency_ms,
                tokens_in=event.tokens_in,
                tokens_out=event.tokens_out,
                error_code=event.error_code,
                model=event.model,
            )
        )
        accepted += 1
    for event in body.quality:
        flag = flags.get(event.flag_key)
        if flag is None:
            continue
        db.add(
            QualityEvent(
                flag_id=flag.id,
                user_key=event.user_key,
                variant_key=event.variant_key,
                score=event.score,
                source=event.source,
                comment=event.comment,
            )
        )
        accepted += 1
    db.commit()
    if accepted == 0 and (body.impressions or body.generations or body.quality):
        raise HTTPException(status_code=400, detail="No matching flags for events")
    return {"accepted": accepted}
