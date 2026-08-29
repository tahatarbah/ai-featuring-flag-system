from aiflag.engine.gates import ArmStats, SLOSpec, check_flag_gates, check_slo


def _slo(metric: str, threshold: float, action: str = "pause", min_samples: int = 20) -> SLOSpec:
    return SLOSpec(metric=metric, threshold=threshold, min_samples=min_samples, action=action)


def test_gate_noop_under_min_samples():
    slos = [_slo("error_rate", 0.05)]
    control = ArmStats(samples=5, error_rate=0.0)
    treatment = ArmStats(samples=100, error_rate=1.0)
    result = check_flag_gates(slos, control, treatment, auto_advance=True, at_max_stage=False)
    assert result.action == "skip"
    assert result.ok


def test_gate_pause_on_error_rate():
    slos = [_slo("error_rate", 0.05, action="pause")]
    control = ArmStats(samples=40, error_rate=0.02)
    treatment = ArmStats(samples=40, error_rate=0.20)
    result = check_flag_gates(slos, control, treatment, auto_advance=False, at_max_stage=False)
    assert result.ok is False
    assert result.action == "pause"
    assert "error_rate" in result.reason


def test_gate_rollback_preferred_over_pause():
    slos = [
        _slo("error_rate", 0.05, action="pause"),
        _slo("judge_mean", 0.4, action="rollback"),
    ]
    control = ArmStats(samples=40, error_rate=0.0, judge_mean=4.5, judge_samples=40)
    treatment = ArmStats(samples=40, error_rate=0.2, judge_mean=3.0, judge_samples=40)
    result = check_flag_gates(slos, control, treatment, auto_advance=True, at_max_stage=False)
    assert result.action == "rollback"


def test_gate_advance_when_healthy():
    slos = [_slo("error_rate", 0.05), _slo("latency_p95", 0.30)]
    control = ArmStats(samples=40, error_rate=0.05, latency_p95=800)
    treatment = ArmStats(samples=40, error_rate=0.04, latency_p95=820)
    result = check_flag_gates(slos, control, treatment, auto_advance=True, at_max_stage=False)
    assert result.action == "advance"
    assert result.ok


def test_latency_relative_increase():
    slo = _slo("latency_p95", 0.30)
    control = ArmStats(samples=20, latency_p95=100)
    treatment = ArmStats(samples=20, latency_p95=150)
    ok, reason = check_slo(slo, control, treatment)
    assert ok is False
    assert "latency_p95" in reason


def test_judge_mean_drop():
    slo = _slo("judge_mean", 0.4)
    control = ArmStats(samples=20, judge_mean=4.2, judge_samples=20)
    treatment = ArmStats(samples=20, judge_mean=3.5, judge_samples=20)
    ok, _ = check_slo(slo, control, treatment)
    assert ok is False
