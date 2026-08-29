from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from aiflag.api.audit import flag_state, write_audit
from aiflag.api.deps import require_admin
from aiflag.api.serialize import apply_percentage, serialize_flag
from aiflag.db import get_db
from aiflag.engine import next_stage_bps, stage_for_bps
from aiflag.models import Flag, FlagStatus, FlagVariant, QualitySLO, Rollout, TargetingRule
from aiflag.schemas import FlagCreate, FlagOut, FlagUpdate, RuleIn, SLOIn, VariantIn

router = APIRouter(prefix="/api/v1/flags", tags=["flags"])

_FLAG_LOAD = (
    joinedload(Flag.variants),
    joinedload(Flag.rules),
    joinedload(Flag.rollout),
    joinedload(Flag.slos),
)


def _get_flag(db: Session, flag_id) -> Flag:
    flag = db.query(Flag).options(*_FLAG_LOAD).filter(Flag.id == flag_id).first()
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag


@router.get("", response_model=list[FlagOut])
def list_flags(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> list[FlagOut]:
    flags = db.query(Flag).options(*_FLAG_LOAD).filter(Flag.archived.is_(False)).order_by(Flag.key).all()
    return [serialize_flag(f) for f in flags]


@router.post("", response_model=FlagOut, status_code=201)
def create_flag(
    body: FlagCreate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    if db.query(Flag).filter(Flag.key == body.key).first():
        raise HTTPException(status_code=409, detail="Flag key already exists")
    if not any(v.is_control for v in body.variants):
        raise HTTPException(status_code=400, detail="At least one control variant is required")

    flag = Flag(
        key=body.key,
        name=body.name,
        description=body.description,
        flag_type=body.flag_type,
        status=FlagStatus.draft.value,
    )
    db.add(flag)
    db.flush()

    key_to_variant: dict[str, FlagVariant] = {}
    for variant in body.variants:
        row = FlagVariant(
            flag_id=flag.id,
            key=variant.key,
            is_control=variant.is_control,
            payload=variant.payload,
        )
        db.add(row)
        db.flush()
        key_to_variant[variant.key] = row

    for rule in body.rules:
        variant = key_to_variant.get(rule.variant_key)
        if variant is None:
            raise HTTPException(status_code=400, detail=f"Unknown variant {rule.variant_key}")
        db.add(
            TargetingRule(
                flag_id=flag.id,
                priority=rule.priority,
                attribute=rule.attribute,
                op=rule.op,
                value=rule.value,
                variant_id=variant.id,
            )
        )

    db.add(
        Rollout(
            flag_id=flag.id,
            percentage_bps=max(0, min(10_000, body.percentage_bps)),
            stage=stage_for_bps(body.percentage_bps),
            auto_advance=body.auto_advance,
        )
    )
    for slo in body.slos:
        db.add(
            QualitySLO(
                flag_id=flag.id,
                metric=slo.metric,
                comparator=slo.comparator,
                threshold=slo.threshold,
                min_samples=slo.min_samples,
                action=slo.action,
            )
        )
    write_audit(db, actor=actor, action="flag.create", flag_id=flag.id, after={"key": flag.key})
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.get("/{flag_id}", response_model=FlagOut)
def get_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    return serialize_flag(_get_flag(db, flag_id))


@router.patch("/{flag_id}", response_model=FlagOut)
def update_flag(
    flag_id: str,
    body: FlagUpdate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    before = flag_state(flag)
    if body.name is not None:
        flag.name = body.name
    if body.description is not None:
        flag.description = body.description
    if body.status is not None:
        flag.status = body.status
        if body.status == FlagStatus.active.value and flag.kill_switch:
            flag.kill_switch = False
        if body.status == FlagStatus.killed.value:
            flag.kill_switch = True
    if body.kill_switch is not None:
        flag.kill_switch = body.kill_switch
        if body.kill_switch:
            flag.status = FlagStatus.killed.value
        elif flag.status == FlagStatus.killed.value:
            flag.status = FlagStatus.paused.value
    if body.salt is not None:
        flag.salt = body.salt
    if flag.rollout:
        if body.auto_advance is not None:
            flag.rollout.auto_advance = body.auto_advance
        if body.percentage_bps is not None:
            apply_percentage(flag, body.percentage_bps)
    write_audit(db, actor=actor, action="flag.update", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.post("/{flag_id}/publish", response_model=FlagOut)
def publish_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    before = flag_state(flag)
    flag.status = FlagStatus.active.value
    flag.kill_switch = False
    write_audit(db, actor=actor, action="flag.publish", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.post("/{flag_id}/kill", response_model=FlagOut)
def kill_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    before = flag_state(flag)
    flag.kill_switch = True
    flag.status = FlagStatus.killed.value
    write_audit(db, actor=actor, action="flag.kill", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.post("/{flag_id}/restore", response_model=FlagOut)
def restore_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    before = flag_state(flag)
    flag.kill_switch = False
    flag.status = FlagStatus.draft.value
    write_audit(db, actor=actor, action="flag.restore", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.post("/{flag_id}/pause", response_model=FlagOut)
def pause_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    before = flag_state(flag)
    flag.status = FlagStatus.paused.value
    write_audit(db, actor=actor, action="flag.pause", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.post("/{flag_id}/advance", response_model=FlagOut)
def advance_flag(
    flag_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    if not flag.rollout:
        raise HTTPException(status_code=400, detail="Flag has no rollout")
    nxt = next_stage_bps(flag.rollout.percentage_bps)
    if nxt is None:
        return serialize_flag(flag)
    before = flag_state(flag)
    apply_percentage(flag, nxt)
    write_audit(db, actor=actor, action="flag.advance", flag_id=flag.id, before=before, after=flag_state(flag))
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.put("/{flag_id}/rules", response_model=FlagOut)
def replace_rules(
    flag_id: str,
    rules: list[RuleIn],
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    key_to_id = {v.key: v.id for v in flag.variants}
    db.query(TargetingRule).filter(TargetingRule.flag_id == flag.id).delete()
    for rule in rules:
        variant_id = key_to_id.get(rule.variant_key)
        if variant_id is None:
            raise HTTPException(status_code=400, detail=f"Unknown variant {rule.variant_key}")
        db.add(
            TargetingRule(
                flag_id=flag.id,
                priority=rule.priority,
                attribute=rule.attribute,
                op=rule.op,
                value=rule.value,
                variant_id=variant_id,
            )
        )
    write_audit(db, actor=actor, action="flag.rules", flag_id=flag.id, after={"count": len(rules)})
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.put("/{flag_id}/variants", response_model=FlagOut)
def replace_variants(
    flag_id: str,
    variants: list[VariantIn],
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    if not any(v.is_control for v in variants):
        raise HTTPException(status_code=400, detail="At least one control variant is required")
    db.query(TargetingRule).filter(TargetingRule.flag_id == flag.id).delete()
    db.query(FlagVariant).filter(FlagVariant.flag_id == flag.id).delete()
    for variant in variants:
        db.add(
            FlagVariant(
                flag_id=flag.id,
                key=variant.key,
                is_control=variant.is_control,
                payload=variant.payload,
            )
        )
    write_audit(db, actor=actor, action="flag.variants", flag_id=flag.id, after={"count": len(variants)})
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))


@router.put("/{flag_id}/slos", response_model=FlagOut)
def replace_slos(
    flag_id: str,
    slos: list[SLOIn],
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str, Depends(require_admin)],
) -> FlagOut:
    flag = _get_flag(db, flag_id)
    db.query(QualitySLO).filter(QualitySLO.flag_id == flag.id).delete()
    for slo in slos:
        db.add(
            QualitySLO(
                flag_id=flag.id,
                metric=slo.metric,
                comparator=slo.comparator,
                threshold=slo.threshold,
                min_samples=slo.min_samples,
                action=slo.action,
            )
        )
    write_audit(db, actor=actor, action="flag.slos", flag_id=flag.id, after={"count": len(slos)})
    db.commit()
    return serialize_flag(_get_flag(db, flag.id))
