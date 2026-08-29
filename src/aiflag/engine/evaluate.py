from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

STAGES_PCT = (0, 1, 5, 25, 50, 100)
STAGES_BPS = tuple(p * 100 for p in STAGES_PCT)


def bucket(salt: str, flag_key: str, user_key: str) -> int:
    """Sticky assignment bucket in [0, 9999]."""
    digest = hashlib.sha256(f"{salt}:{flag_key}:{user_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


def stage_for_bps(percentage_bps: int) -> int:
    for i, bps in enumerate(STAGES_BPS):
        if percentage_bps <= bps:
            return i
    return len(STAGES_BPS) - 1


def next_stage_bps(percentage_bps: int) -> int | None:
    for bps in STAGES_BPS:
        if bps > percentage_bps:
            return bps
    return None


@dataclass
class VariantSnapshot:
    key: str
    is_control: bool
    payload: dict[str, Any]


@dataclass
class RuleSnapshot:
    priority: int
    attribute: str
    op: str
    value: str
    variant_key: str


@dataclass
class FlagSnapshot:
    key: str
    flag_type: str
    status: str
    kill_switch: bool
    salt: str
    archived: bool = False
    variants: list[VariantSnapshot] = field(default_factory=list)
    rules: list[RuleSnapshot] = field(default_factory=list)
    percentage_bps: int = 0


@dataclass
class Evaluation:
    flag_key: str
    variant_key: str
    payload: dict[str, Any]
    reason: str
    bucket: int | None = None


def _control(flag: FlagSnapshot) -> VariantSnapshot | None:
    for variant in flag.variants:
        if variant.is_control:
            return variant
    return flag.variants[0] if flag.variants else None


def _treatment(flag: FlagSnapshot) -> VariantSnapshot | None:
    for variant in flag.variants:
        if not variant.is_control:
            return variant
    return None


def _variant_by_key(flag: FlagSnapshot, key: str) -> VariantSnapshot | None:
    for variant in flag.variants:
        if variant.key == key:
            return variant
    return None


def _empty(flag_key: str, reason: str) -> Evaluation:
    return Evaluation(flag_key=flag_key, variant_key="off", payload={}, reason=reason)


def _from_variant(
    flag_key: str, variant: VariantSnapshot, reason: str, bucket_n: int | None = None
) -> Evaluation:
    return Evaluation(
        flag_key=flag_key,
        variant_key=variant.key,
        payload=dict(variant.payload),
        reason=reason,
        bucket=bucket_n,
    )


def _attr_value(attributes: dict[str, Any], name: str) -> str | None:
    if name not in attributes or attributes[name] is None:
        return None
    return str(attributes[name])


def _rule_matches(rule: RuleSnapshot, attributes: dict[str, Any]) -> bool:
    raw = _attr_value(attributes, rule.attribute)
    if raw is None:
        return False
    op = rule.op.lower()
    if op == "eq":
        return raw == rule.value
    if op == "in":
        allowed = [part.strip() for part in rule.value.split(",") if part.strip()]
        return raw in allowed
    if op == "contains":
        return rule.value in raw
    return False


def evaluate(
    flag: FlagSnapshot | None,
    user_key: str,
    attributes: dict[str, Any] | None = None,
) -> Evaluation:
    attrs = dict(attributes or {})
    attrs.setdefault("user", user_key)

    if flag is None or flag.archived:
        return _empty(flag.key if flag else "unknown", "FLAG_NOT_FOUND")

    control = _control(flag)
    if control is None:
        return _empty(flag.key, "FLAG_NOT_FOUND")

    if flag.kill_switch or flag.status == "killed":
        return _from_variant(flag.key, control, "KILL_SWITCH")

    if flag.status in {"paused", "draft"}:
        return _from_variant(flag.key, control, "FLAG_INACTIVE")

    rules = sorted(flag.rules, key=lambda r: r.priority)
    for rule in rules:
        if _rule_matches(rule, attrs):
            targeted = _variant_by_key(flag, rule.variant_key)
            if targeted is not None:
                return _from_variant(flag.key, targeted, "TARGETING_MATCH")

    treatment = _treatment(flag)
    bucket_n = bucket(flag.salt, flag.key, user_key)
    if treatment is not None and bucket_n < flag.percentage_bps:
        return _from_variant(flag.key, treatment, "PERCENTAGE_ROLLOUT", bucket_n)
    return _from_variant(flag.key, control, "DEFAULT", bucket_n)


def snapshot_from_orm(flag: Any) -> FlagSnapshot:
    """Build a FlagSnapshot from a SQLAlchemy Flag with relationships loaded."""
    variants = [
        VariantSnapshot(key=v.key, is_control=v.is_control, payload=dict(v.payload or {}))
        for v in flag.variants
    ]
    variant_id_to_key = {v.id: v.key for v in flag.variants}
    rules = [
        RuleSnapshot(
            priority=r.priority,
            attribute=r.attribute,
            op=r.op,
            value=r.value,
            variant_key=variant_id_to_key.get(r.variant_id, ""),
        )
        for r in flag.rules
    ]
    percentage_bps = flag.rollout.percentage_bps if flag.rollout else 0
    return FlagSnapshot(
        key=flag.key,
        flag_type=flag.flag_type,
        status=flag.status,
        kill_switch=flag.kill_switch,
        salt=flag.salt,
        archived=flag.archived,
        variants=variants,
        rules=rules,
        percentage_bps=percentage_bps,
    )
