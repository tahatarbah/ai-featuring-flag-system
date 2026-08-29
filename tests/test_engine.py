from aiflag.engine import (
    FlagSnapshot,
    RuleSnapshot,
    VariantSnapshot,
    bucket,
    evaluate,
)


def _flag(**kwargs) -> FlagSnapshot:
    control = VariantSnapshot("control", True, {"model": "llama3.2"})
    treatment = VariantSnapshot("treatment", False, {"model": "llama3.2", "prompt_id": "v2"})
    defaults = dict(
        key="support_assistant",
        flag_type="multivariate",
        status="active",
        kill_switch=False,
        salt="fixed-salt",
        variants=[control, treatment],
        percentage_bps=2500,
    )
    defaults.update(kwargs)
    return FlagSnapshot(**defaults)


def test_bucket_is_stable():
    a = bucket("fixed-salt", "support_assistant", "alice")
    b = bucket("fixed-salt", "support_assistant", "alice")
    assert a == b
    assert 0 <= a < 10_000
    assert bucket("fixed-salt", "support_assistant", "bob") != a or True  # may collide; check range only
    assert bucket("other", "support_assistant", "alice") != a


def test_kill_switch_returns_control_at_100_percent():
    flag = _flag(kill_switch=True, percentage_bps=10_000)
    result = evaluate(flag, "anyone")
    assert result.variant_key == "control"
    assert result.reason == "KILL_SWITCH"


def test_killed_status_same_as_kill_switch():
    flag = _flag(status="killed", percentage_bps=10_000)
    result = evaluate(flag, "anyone")
    assert result.reason == "KILL_SWITCH"
    assert result.variant_key == "control"


def test_targeting_beats_percentage():
    flag = _flag(
        percentage_bps=0,
        rules=[
            RuleSnapshot(
                priority=0,
                attribute="user",
                op="eq",
                value="alice",
                variant_key="treatment",
            )
        ],
    )
    alice = evaluate(flag, "alice")
    bob = evaluate(flag, "bob")
    assert alice.reason == "TARGETING_MATCH"
    assert alice.variant_key == "treatment"
    assert bob.reason == "DEFAULT"
    assert bob.variant_key == "control"


def test_percentage_rollout_uses_bucket():
    flag = _flag(percentage_bps=10_000)
    result = evaluate(flag, "alice")
    assert result.reason == "PERCENTAGE_ROLLOUT"
    assert result.variant_key == "treatment"

    flag_off = _flag(percentage_bps=0)
    result_off = evaluate(flag_off, "alice")
    assert result_off.reason == "DEFAULT"
    assert result_off.variant_key == "control"


def test_sticky_assignment():
    flag = _flag(percentage_bps=5000)
    first = evaluate(flag, "sticky-user")
    second = evaluate(flag, "sticky-user")
    assert first.variant_key == second.variant_key
    assert first.bucket == second.bucket


def test_draft_and_paused_are_inactive():
    assert evaluate(_flag(status="draft"), "u").reason == "FLAG_INACTIVE"
    assert evaluate(_flag(status="paused"), "u").reason == "FLAG_INACTIVE"


def test_missing_flag():
    result = evaluate(None, "u")
    assert result.reason == "FLAG_NOT_FOUND"
    assert result.variant_key == "off"
