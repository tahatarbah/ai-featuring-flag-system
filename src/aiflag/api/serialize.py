from __future__ import annotations

from aiflag.engine import stage_for_bps
from aiflag.models import Flag
from aiflag.schemas import FlagOut, RuleOut, RolloutOut, SLOOut, VariantOut


def serialize_flag(flag: Flag) -> FlagOut:
    variant_id_to_key = {v.id: v.key for v in flag.variants}
    rules = [
        RuleOut(
            id=r.id,
            priority=r.priority,
            attribute=r.attribute,
            op=r.op,
            value=r.value,
            variant_id=r.variant_id,
            variant_key=variant_id_to_key.get(r.variant_id, ""),
        )
        for r in flag.rules
    ]
    rollout = None
    if flag.rollout:
        rollout = RolloutOut(
            percentage_bps=flag.rollout.percentage_bps,
            stage=flag.rollout.stage,
            auto_advance=flag.rollout.auto_advance,
            last_action_at=flag.rollout.last_action_at,
        )
    return FlagOut(
        id=flag.id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        flag_type=flag.flag_type,
        status=flag.status,
        kill_switch=flag.kill_switch,
        salt=flag.salt,
        archived=flag.archived,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
        variants=[
            VariantOut(id=v.id, key=v.key, is_control=v.is_control, payload=v.payload or {})
            for v in flag.variants
        ],
        rules=rules,
        rollout=rollout,
        slos=[
            SLOOut(
                id=s.id,
                metric=s.metric,
                comparator=s.comparator,
                threshold=s.threshold,
                min_samples=s.min_samples,
                action=s.action,
            )
            for s in flag.slos
        ],
    )


def apply_percentage(flag: Flag, percentage_bps: int) -> None:
    bps = max(0, min(10_000, int(percentage_bps)))
    if flag.rollout:
        flag.rollout.percentage_bps = bps
        flag.rollout.stage = stage_for_bps(bps)
