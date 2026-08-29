from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ArmStats:
    samples: int = 0
    error_rate: float = 0.0
    latency_p95: float = 0.0
    judge_mean: float = 0.0
    tokens_per_request: float = 0.0
    judge_samples: int = 0


@dataclass
class SLOSpec:
    metric: str
    threshold: float
    min_samples: int
    action: str


@dataclass
class GateResult:
    ok: bool
    action: str  # pass | skip | pause | rollback | advance
    reason: str
    metrics: dict[str, Any]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] * (1 - frac) + ordered[high] * frac)


def check_slo(slo: SLOSpec, control: ArmStats, treatment: ArmStats) -> tuple[bool, str]:
    needed = slo.min_samples
    if slo.metric == "judge_mean":
        if control.judge_samples < needed or treatment.judge_samples < needed:
            return True, "insufficient_samples"
    elif control.samples < needed or treatment.samples < needed:
        return True, "insufficient_samples"

    metric = slo.metric
    if metric == "error_rate":
        delta = treatment.error_rate - control.error_rate
        if delta > slo.threshold:
            return False, f"error_rate delta {delta:.3f} exceeds {slo.threshold}"
        return True, "ok"
    if metric == "latency_p95":
        if control.latency_p95 <= 0:
            return True, "ok"
        ratio = (treatment.latency_p95 - control.latency_p95) / control.latency_p95
        if ratio > slo.threshold:
            return False, f"latency_p95 relative increase {ratio:.3f} exceeds {slo.threshold}"
        return True, "ok"
    if metric == "judge_mean":
        drop = control.judge_mean - treatment.judge_mean
        if drop > slo.threshold:
            return False, f"judge_mean drop {drop:.3f} exceeds {slo.threshold}"
        return True, "ok"
    if metric == "tokens_per_request":
        if control.tokens_per_request <= 0:
            return True, "ok"
        ratio = treatment.tokens_per_request / control.tokens_per_request
        if ratio > slo.threshold:
            return False, f"tokens_per_request ratio {ratio:.3f} exceeds {slo.threshold}"
        return True, "ok"
    return True, f"unknown_metric:{metric}"


def check_flag_gates(
    slos: list[SLOSpec],
    control: ArmStats,
    treatment: ArmStats,
    *,
    auto_advance: bool,
    at_max_stage: bool,
) -> GateResult:
    metrics = {"control": asdict(control), "treatment": asdict(treatment)}
    min_needed = min((s.min_samples for s in slos), default=20)
    if control.samples < min_needed or treatment.samples < min_needed:
        return GateResult(ok=True, action="skip", reason="insufficient_samples", metrics=metrics)

    failures: list[tuple[SLOSpec, str]] = []
    for slo in slos:
        ok, reason = check_slo(slo, control, treatment)
        if not ok:
            failures.append((slo, reason))

    if failures:
        action = "rollback" if any(s.action == "rollback" for s, _ in failures) else "pause"
        joined = "; ".join(reason for _, reason in failures)
        return GateResult(ok=False, action=action, reason=joined, metrics=metrics)

    if auto_advance and not at_max_stage:
        return GateResult(ok=True, action="advance", reason="all_slos_passed", metrics=metrics)
    return GateResult(ok=True, action="pass", reason="all_slos_passed", metrics=metrics)
