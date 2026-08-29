from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.orm import Session, joinedload

from aiflag.api.audit import flag_state, utcnow, write_audit
from aiflag.api.routers.quality import collect_arm_stats
from aiflag.api.serialize import apply_percentage
from aiflag.config import settings
from aiflag.db import SessionLocal
from aiflag.engine import next_stage_bps
from aiflag.engine.gates import SLOSpec, check_flag_gates
from aiflag.models import Flag, FlagStatus, GateDecision

log = logging.getLogger(__name__)


def evaluate_flag_gates(db: Session, flag: Flag) -> GateDecision | None:
    if flag.status != FlagStatus.active.value or flag.kill_switch:
        return None
    if not flag.rollout or not flag.slos:
        return None

    control = next((v for v in flag.variants if v.is_control), None)
    treatment = next((v for v in flag.variants if not v.is_control), None)
    if control is None or treatment is None:
        return None

    since = utcnow() - timedelta(minutes=settings.gate_window_minutes)
    control_stats, treatment_stats = collect_arm_stats(
        db, flag.id, control.key, treatment.key, since
    )
    slos = [
        SLOSpec(
            metric=s.metric,
            threshold=s.threshold,
            min_samples=s.min_samples,
            action=s.action,
        )
        for s in flag.slos
    ]
    at_max = next_stage_bps(flag.rollout.percentage_bps) is None
    result = check_flag_gates(
        slos,
        control_stats,
        treatment_stats,
        auto_advance=flag.rollout.auto_advance,
        at_max_stage=at_max,
    )

    cooldown = flag.rollout.last_action_at
    if result.action in {"advance", "pause", "rollback"} and cooldown:
        if utcnow() - cooldown < timedelta(minutes=settings.gate_window_minutes):
            if result.action == "advance":
                result.action = "pass"
                result.reason = "advance_cooldown"
            else:
                return None

    if result.action in {"skip", "pass"}:
        return None

    before = flag_state(flag)
    if result.action == "pause":
        flag.status = FlagStatus.paused.value
        flag.rollout.last_action_at = utcnow()
    elif result.action == "rollback":
        flag.status = FlagStatus.paused.value
        apply_percentage(flag, 0)
        flag.rollout.last_action_at = utcnow()
    elif result.action == "advance":
        nxt = next_stage_bps(flag.rollout.percentage_bps)
        if nxt is None:
            return None
        apply_percentage(flag, nxt)
        flag.rollout.last_action_at = utcnow()

    write_audit(
        db,
        actor="gate-worker",
        action=f"gate.{result.action}",
        flag_id=flag.id,
        before=before,
        after=flag_state(flag),
    )
    decision = GateDecision(
        flag_id=flag.id,
        action=result.action,
        reason=result.reason,
        metrics=result.metrics,
    )
    db.add(decision)
    return decision


def run_gate_pass() -> int:
    db = SessionLocal()
    acted = 0
    try:
        flags = (
            db.query(Flag)
            .options(
                joinedload(Flag.variants),
                joinedload(Flag.rollout),
                joinedload(Flag.slos),
            )
            .filter(Flag.archived.is_(False), Flag.status == FlagStatus.active.value)
            .all()
        )
        for flag in flags:
            decision = evaluate_flag_gates(db, flag)
            if decision and decision.action in {"pause", "rollback", "advance"}:
                acted += 1
        db.commit()
    except Exception:
        db.rollback()
        log.exception("gate pass failed")
    finally:
        db.close()
    return acted


async def gate_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(run_gate_pass)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.gate_interval_seconds)
        except TimeoutError:
            continue
