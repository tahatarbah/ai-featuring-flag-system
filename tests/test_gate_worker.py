from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from aiflag.engine import stage_for_bps
from aiflag.workers.gates import evaluate_flag_gates


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, generations, quality):
        self.generations = generations
        self.quality = quality
        self.added = []

    def query(self, model):
        name = model.__name__
        if name == "GenerationEvent":
            return FakeQuery(self.generations)
        if name == "QualityEvent":
            return FakeQuery(self.quality)
        return FakeQuery([])

    def add(self, row):
        self.added.append(row)


def _flag(status="active", percentage_bps=2500, auto_advance=False):
    control = SimpleNamespace(id=uuid4(), key="control", is_control=True)
    treatment = SimpleNamespace(id=uuid4(), key="treatment", is_control=False)
    slo = SimpleNamespace(metric="error_rate", threshold=0.05, min_samples=5, action="rollback")
    rollout = SimpleNamespace(
        percentage_bps=percentage_bps,
        stage=stage_for_bps(percentage_bps),
        auto_advance=auto_advance,
        last_action_at=None,
    )
    return SimpleNamespace(
        id=uuid4(),
        key="support_assistant",
        status=status,
        kill_switch=False,
        variants=[control, treatment],
        slos=[slo],
        rollout=rollout,
    )


def _gen(variant, error=None):
    return SimpleNamespace(
        variant_key=variant,
        latency_ms=100,
        tokens_in=10,
        tokens_out=20,
        error_code=error,
        ts=datetime.now(timezone.utc),
    )


def test_rollback_sets_percentage_zero(monkeypatch):
    flag = _flag()
    gens = [_gen("control") for _ in range(10)] + [_gen("treatment", error="boom") for _ in range(10)]
    db = FakeDB(gens, [])

    decision = evaluate_flag_gates(db, flag)
    assert decision is not None
    assert decision.action == "rollback"
    assert flag.rollout.percentage_bps == 0
    assert flag.status == "paused"
    assert any(getattr(x, "action", "") == "gate.rollback" for x in db.added)


def test_inactive_flag_skipped():
    flag = _flag(status="paused")
    db = FakeDB([], [])
    assert evaluate_flag_gates(db, flag) is None
