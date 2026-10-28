"""Deterministic test-provenance decisions, never production benchmark claims."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from backend.compiler.router_optimizer import optimize
from backend.config import BackendConfig
from backend.schemas import LocalBenchmarkCase, OptimizationResult, RoutingDecision


def test_lowest_cost_eligible_candidate_and_historical_savings(optimization_environment):
    sample = optimization_environment.build_optimization()
    result = optimize(sample.snapshot)
    decision = result.decisions[0]
    assert result.status == "complete" and result.decisions_complete and result.nodes_recommended == 1
    assert decision.status == "recommended" and decision.selected_model_id == "local/candidate"
    assert decision.differs_from_baseline and decision.recorded_savings_usd == Decimal("1.00")
    assert result.provenance == decision.provenance == "test"
    assert decision.candidates[0].cost_total_usd == Decimal("2.00")
    assert decision.candidates[1].quality_pass_rate == 1
    assert all(candidate.latency_ms.mean is None and candidate.latency_ms.sample_count == 0 for candidate in decision.candidates)
    assert "PRIVATE_" not in result.model_dump_json()
    assert result.model_dump_json() == optimize(sample.snapshot).model_dump_json()
    assert OptimizationResult.model_validate_json(result.model_dump_json()) == result


def test_cheaper_model_with_failed_required_evaluation_is_excluded(optimization_environment):
    env = optimization_environment
    outputs = {(model.identifier, case): ("wrong-test-output" if model.identifier == "local/candidate" else expected)
               for model in env.registry.document.models for case, expected in (("case-one", "PRIVATE_CAPTURE_ONE"), ("case-two", "PRIVATE_CAPTURE_TWO"))}
    sample = env.build_optimization(outputs=outputs)
    result = optimize(sample.snapshot)
    decision = result.decisions[0]
    assert decision.status == "baseline_retained" and decision.reason == "no_eligible_alternative"
    assert decision.selected_model_id == "local/baseline" and decision.recorded_savings_usd == 0
    assert decision.candidates[1].eligibility == "rejected" and "quality_failed" in decision.candidates[1].reasons


@pytest.mark.parametrize("missing_model", ["local/baseline", "local/candidate"])
def test_missing_cost_never_yields_a_cost_based_selection(optimization_environment, missing_model):
    rates = {"local/baseline": "1", "local/candidate": "0.5", missing_model: None}
    decision = optimize(optimization_environment.build_optimization(rates=rates).snapshot).decisions[0]
    assert decision.status == "inconclusive" and decision.selected_model_id is None
    assert decision.recorded_savings_usd is None and not decision.differs_from_baseline
    assert "cost_unavailable" in next(item for item in decision.candidates if item.model.identifier == missing_model).reasons


@pytest.mark.parametrize("missing_model", ["local/baseline", "local/candidate"])
def test_missing_baseline_or_candidate_output_blocks_selection(optimization_environment, missing_model):
    env = optimization_environment
    outputs = {(model.identifier, case): (None if model.identifier == missing_model else expected)
               for model in env.registry.document.models for case, expected in (("case-one", "PRIVATE_CAPTURE_ONE"), ("case-two", "PRIVATE_CAPTURE_TWO"))}
    result = optimize(env.build_optimization(outputs=outputs).snapshot)
    assert result.status == "inconclusive" and not result.decisions_complete
    decision = result.decisions[0]
    assert decision.selected_model_id is None and decision.reason == ("baseline_ineligible" if missing_model.endswith("baseline") else "candidate_evidence_incomplete")
    assert next(item for item in decision.candidates if item.model.identifier == missing_model).quality_pass_rate is None


def test_missing_ground_truth_remains_inconclusive(optimization_environment):
    env = optimization_environment
    cases = [LocalBenchmarkCase(identifier="one", input_text="test", expected_output=None)]
    outputs = {(model.identifier, "one"): "test-output" for model in env.registry.document.models}
    result = optimize(env.build_optimization(cases=cases, outputs=outputs).snapshot)
    assert result.nodes_inconclusive == 1 and result.nodes_eligible == 0
    assert all(item.quality_pass_rate is None for item in result.decisions[0].candidates)


@pytest.mark.parametrize("rate", ["1.00", "2.00", "0"])
def test_cost_ties_and_more_expensive_alternatives_retain_baseline(optimization_environment, rate):
    base = "0" if rate == "0" else "1.00"
    decision = optimize(optimization_environment.build_optimization(rates={"local/baseline": base, "local/candidate": rate}).snapshot).decisions[0]
    assert decision.status == "baseline_retained" and decision.selected_model_id == "local/baseline"
    assert decision.recorded_savings_usd == 0


def test_decimal_comparison_and_serialization_ignore_ambient_precision(optimization_environment):
    sample = optimization_environment.build_optimization(tokens=1, rates={"local/baseline": "0.100000000002", "local/candidate": "0.100000000001"})
    expected = optimize(sample.snapshot)
    with localcontext() as context:
        context.prec = 2
        actual = optimize(sample.snapshot)
        assert context.prec == 2
    assert actual == expected
    assert actual.decisions[0].recorded_savings_usd == Decimal("0.000000000000000002")


def test_threshold_is_explicit_and_never_a_mock_ui_default(optimization_environment):
    sample = optimization_environment.build_optimization()
    result = optimize(replace(sample.snapshot, quality_threshold=None))
    assert result.status == "unavailable" and result.diagnostics == ("threshold_unconfigured",)
    assert result.decisions[0].selected_model_id is None
    assert BackendConfig().optimization_quality_threshold is None
    assert BackendConfig(optimization_quality_threshold="0.92").optimization_quality_threshold == Decimal("0.92")


@pytest.mark.parametrize("value", [0.92, True, "NaN", "1.1", "-0.1", "0.1234567"])
def test_threshold_rejects_ambiguous_or_invalid_configuration(value):
    with pytest.raises(ValidationError):
        BackendConfig(optimization_quality_threshold=value)


def test_unresolved_decision_cannot_assert_model_or_savings(optimization_environment):
    result = optimize(optimization_environment.build_optimization(rates={"local/baseline": None, "local/candidate": "0.5"}).snapshot)
    decision = result.decisions[0]
    for changes in ({"selected_model_id": "local/candidate"}, {"recorded_savings_usd": "0"}, {"differs_from_baseline": True}):
        with pytest.raises(ValidationError):
            RoutingDecision.model_validate({**decision.model_dump(), **changes})


def test_cancellation_check_is_observed_during_pure_optimization(optimization_environment):
    sample = optimization_environment.build_optimization()
    calls = []
    def check():
        calls.append(True)
        if len(calls) == 2:
            raise TimeoutError("test deadline")
    with pytest.raises(TimeoutError):
        optimize(sample.snapshot, check)
    assert len(calls) == 2


def test_legacy_measurement_flags_without_offline_evidence_are_inconclusive(job_environment):
    from backend.compiler.router_optimizer import OptimizationSnapshot
    from backend.schemas import BenchmarkSummary
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    env.storage.transition_job(job.run_id, ("queued",), status="running")
    for key in plan.unit_keys():
        env.storage.transition_job(job.run_id, ("running",), measurement=env.measurement(key, evaluation_status="passed"))
    job = env.storage.transition_job(job.run_id, ("running",), status="complete", result=BenchmarkSummary(provenance="test", evaluation_status="passed"))
    result = optimize(OptimizationSnapshot(job, Decimal("0.92"), "a" * 64))
    assert result.status == "inconclusive" and result.decisions[0].selected_model_id is None
    assert all(candidate.passed_cases == 0 and candidate.quality_pass_rate is None for candidate in result.decisions[0].candidates)


def test_unfinished_job_has_no_decision_or_policy(optimization_environment):
    from backend.compiler.policy_generator import generate_policy
    env = optimization_environment
    sample = env.build_optimization()
    queued = env.storage.create_job(env.request, sample.job.plan, lambda _: None)
    result = optimize(replace(sample.snapshot, job=queued))
    assert result.status == "unavailable" and result.diagnostics == ("benchmark_incomplete",)
    assert generate_policy(result).yaml_content is None


def test_measurement_digest_is_independent_of_completion_order(optimization_environment):
    from backend.schemas import JobResponse
    sample = optimization_environment.build_optimization()
    reordered = JobResponse.model_validate({**sample.job.model_dump(), "measurements": tuple(reversed(sample.job.measurements))})
    first = optimize(sample.snapshot).decisions[0]
    second = optimize(replace(sample.snapshot, job=reordered)).decisions[0]
    assert first == second


def test_failure_is_a_hard_exclusion_even_with_a_zero_threshold(optimization_environment):
    env = optimization_environment
    outputs = {(model.identifier, case): "wrong" for model in env.registry.document.models for case in ("case-one", "case-two")}
    sample = env.build_optimization(outputs=outputs)
    result = optimize(replace(sample.snapshot, quality_threshold=Decimal("0")))
    assert result.nodes_eligible == 0 and result.status == "inconclusive"
    assert all(item.eligibility == "rejected" for item in result.decisions[0].candidates)
