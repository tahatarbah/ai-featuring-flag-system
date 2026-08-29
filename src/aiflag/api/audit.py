from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from aiflag.models import AuditLog


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    flag_id=None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(actor=actor, action=action, flag_id=flag_id, before=before, after=after)
    db.add(row)
    return row


def flag_state(flag) -> dict[str, Any]:
    return {
        "key": flag.key,
        "status": flag.status,
        "kill_switch": flag.kill_switch,
        "percentage_bps": flag.rollout.percentage_bps if flag.rollout else 0,
        "auto_advance": flag.rollout.auto_advance if flag.rollout else False,
        "stage": flag.rollout.stage if flag.rollout else 0,
    }
