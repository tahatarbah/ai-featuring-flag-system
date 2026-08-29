from __future__ import annotations

from aiflag.api.deps import hash_sdk_key
from aiflag.config import settings
from aiflag.db import SessionLocal
from aiflag.engine import stage_for_bps
from aiflag.models import Flag, FlagStatus, FlagType, FlagVariant, QualitySLO, Rollout, SdkKey

CONTROL_PROMPT = (
    "You are a concise customer support assistant for an internal tools company. "
    "Answer in 3-6 sentences. If you are unsure, say so and suggest a next step."
)

TREATMENT_PROMPT = (
    "You are a cautious customer support assistant. Prefer safety over speed. "
    "Refuse anything that could leak credentials or internal data. "
    "State assumptions. Offer a short checklist the user can follow. "
    "Keep a calm, precise tone."
)

DEFAULT_SLOS = [
    ("error_rate", 0.05, 20, "pause"),
    ("latency_p95", 0.30, 20, "pause"),
    ("judge_mean", 0.4, 20, "rollback"),
    ("tokens_per_request", 2.0, 20, "pause"),
]


def seed(db=None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        _seed_sdk_key(db)
        _seed_support(db)
        _seed_confidence(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


def _seed_sdk_key(db) -> None:
    digest = hash_sdk_key(settings.sdk_dev_key)
    if db.query(SdkKey).filter(SdkKey.key_hash == digest).first():
        return
    db.add(
        SdkKey(
            name="local-dev",
            key_hash=digest,
            prefix=settings.sdk_dev_key[:12],
        )
    )


def _seed_support(db) -> None:
    if db.query(Flag).filter(Flag.key == "support_assistant").first():
        return
    flag = Flag(
        key="support_assistant",
        name="Support assistant",
        description="Multivariate prompt/model rollout for the demo support assistant.",
        flag_type=FlagType.multivariate.value,
        status=FlagStatus.active.value,
    )
    db.add(flag)
    db.flush()
    db.add(
        FlagVariant(
            flag_id=flag.id,
            key="control",
            is_control=True,
            payload={
                "model": settings.ollama_model,
                "prompt_id": "support_v1",
                "temperature": 0.2,
                "max_tokens": 512,
                "system_prompt": CONTROL_PROMPT,
            },
        )
    )
    db.add(
        FlagVariant(
            flag_id=flag.id,
            key="treatment",
            is_control=False,
            payload={
                "model": settings.ollama_model,
                "prompt_id": "support_v2",
                "temperature": 0.2,
                "max_tokens": 640,
                "system_prompt": TREATMENT_PROMPT,
            },
        )
    )
    db.add(
        Rollout(
            flag_id=flag.id,
            percentage_bps=2500,
            stage=stage_for_bps(2500),
            auto_advance=False,
        )
    )
    for metric, threshold, min_samples, action in DEFAULT_SLOS:
        db.add(
            QualitySLO(
                flag_id=flag.id,
                metric=metric,
                comparator="max_delta",
                threshold=threshold,
                min_samples=min_samples,
                action=action,
            )
        )


def _seed_confidence(db) -> None:
    if db.query(Flag).filter(Flag.key == "show_confidence").first():
        return
    flag = Flag(
        key="show_confidence",
        name="Show confidence",
        description="Boolean flag. Playground shows a confidence line when on.",
        flag_type=FlagType.boolean.value,
        status=FlagStatus.active.value,
    )
    db.add(flag)
    db.flush()
    db.add(
        FlagVariant(
            flag_id=flag.id,
            key="off",
            is_control=True,
            payload={"enabled": False},
        )
    )
    db.add(
        FlagVariant(
            flag_id=flag.id,
            key="on",
            is_control=False,
            payload={"enabled": True},
        )
    )
    db.add(
        Rollout(
            flag_id=flag.id,
            percentage_bps=1000,
            stage=stage_for_bps(1000),
            auto_advance=False,
        )
    )


def main() -> None:
    seed()
    print("Seed complete.")
    print(f"  Admin token: {settings.admin_token}")
    print(f"  SDK key:     {settings.sdk_dev_key}")
    print("  Flags:       support_assistant (25%), show_confidence (10%)")


if __name__ == "__main__":
    main()
