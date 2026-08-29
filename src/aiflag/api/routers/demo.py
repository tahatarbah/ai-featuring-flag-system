from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from aiflag.api.deps import require_admin
from aiflag.db import get_db
from aiflag.demo.ollama import generate_answer, judge_answer
from aiflag.engine import evaluate, snapshot_from_orm
from aiflag.models import Flag, GenerationEvent, Impression, QualityEvent
from pydantic import BaseModel, Field

from aiflag.schemas import AskIn, AskOut, EvaluateOut, ThumbsIn

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

SUPPORT_FLAG = "support_assistant"
CONFIDENCE_FLAG = "show_confidence"


class SimulateIn(BaseModel):
    users: int = Field(default=20, ge=1, le=80)
    question: str = "Our staging deploy is stuck on migrations. What should I check first?"
    prefix: str = "sim"


class SimulateOut(BaseModel):
    asked: int
    variants: dict[str, int]
    errors: int
    avg_judge: float | None = None


@router.post("/ask", response_model=AskOut)
async def ask(
    body: AskIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> AskOut:
    flags = {
        f.key: f
        for f in db.query(Flag)
        .options(joinedload(Flag.variants), joinedload(Flag.rules), joinedload(Flag.rollout))
        .filter(Flag.key.in_([SUPPORT_FLAG, CONFIDENCE_FLAG]))
        .all()
    }
    support = flags.get(SUPPORT_FLAG)
    if support is None:
        raise HTTPException(status_code=400, detail="Seed the support_assistant flag first")

    support_eval = evaluate(snapshot_from_orm(support), body.user_key, body.attributes)
    confidence_flag = flags.get(CONFIDENCE_FLAG)
    confidence_on = False
    if confidence_flag is not None:
        conf_eval = evaluate(snapshot_from_orm(confidence_flag), body.user_key, body.attributes)
        confidence_on = conf_eval.variant_key == "on"
        db.add(
            Impression(
                flag_id=confidence_flag.id,
                user_key=body.user_key,
                variant_key=conf_eval.variant_key,
                reason=conf_eval.reason,
            )
        )

    db.add(
        Impression(
            flag_id=support.id,
            user_key=body.user_key,
            variant_key=support_eval.variant_key,
            reason=support_eval.reason,
        )
    )

    result = await generate_answer(support_eval.payload, body.question)
    db.add(
        GenerationEvent(
            flag_id=support.id,
            user_key=body.user_key,
            variant_key=support_eval.variant_key,
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            error_code=result.error_code,
            model=result.model,
        )
    )

    judge_score = None
    judge_reason = ""
    if result.error_code is None and result.answer:
        judged = await judge_answer(body.question, result.answer)
        judge_score = judged.score
        judge_reason = judged.reason
        db.add(
            QualityEvent(
                flag_id=support.id,
                user_key=body.user_key,
                variant_key=support_eval.variant_key,
                score=judged.score,
                source="judge",
                comment=judged.reason,
            )
        )

    db.commit()
    return AskOut(
        answer=result.answer,
        evaluation=EvaluateOut(
            flag_key=support_eval.flag_key,
            variant_key=support_eval.variant_key,
            payload=support_eval.payload,
            reason=support_eval.reason,
            bucket=support_eval.bucket,
        ),
        confidence_shown=confidence_on,
        judge_score=judge_score,
        judge_reason=judge_reason,
        latency_ms=result.latency_ms,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        error_code=result.error_code,
        model=result.model,
    )


@router.post("/thumbs")
def thumbs(
    body: ThumbsIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> dict[str, str]:
    flag = db.query(Flag).filter(Flag.key == body.flag_key).first()
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    db.add(
        QualityEvent(
            flag_id=flag.id,
            user_key=body.user_key,
            variant_key=body.variant_key,
            score=body.score,
            source="thumbs",
            comment=body.comment,
        )
    )
    db.commit()
    return {"status": "ok"}


@router.post("/simulate", response_model=SimulateOut)
async def simulate(
    body: SimulateIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_admin)],
) -> SimulateOut:
    """Batch playground asks to fill quality charts quickly."""
    variants: dict[str, int] = {}
    errors = 0
    scores: list[float] = []
    for i in range(body.users):
        result = await ask(
            AskIn(user_key=f"{body.prefix}-{i:03d}", question=body.question),
            db,
            _,
        )
        key = result.evaluation.variant_key
        variants[key] = variants.get(key, 0) + 1
        if result.error_code:
            errors += 1
        if result.judge_score is not None:
            scores.append(result.judge_score)
    return SimulateOut(
        asked=body.users,
        variants=variants,
        errors=errors,
        avg_judge=(sum(scores) / len(scores)) if scores else None,
    )
