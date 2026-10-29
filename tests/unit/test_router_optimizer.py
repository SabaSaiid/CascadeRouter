"""Deterministic test-provenance decisions, never production benchmark claims."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from backend.compiler.router_optimizer import optimize
from backend.config import BackendConfig
from backend.schemas import (
    BenchmarkRegistryDocument, BenchmarkRequest, LocalBenchmarkCase, ModelVersion,
    OptimizationResult, RecordingEvidence, RoutingDecision,
)
from backend.services.benchmark_cases import BenchmarkRegistry


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


@pytest.fixture
def cost_selection_case(optimization_environment):
    """Build real optimizer inputs from synthetic, explicitly test-only captures."""
    env = optimization_environment
    env.registry = BenchmarkRegistry(BenchmarkRegistryDocument.model_validate({
        **env.registry.document.model_dump(),
        "models": (*env.registry.document.models, ModelVersion(identifier="local/alternative", version="v1")),
    }))
    env.request = BenchmarkRequest.model_validate({
        **env.request.model_dump(), "candidate_model_ids": ("local/candidate", "local/alternative"),
    })
    make_offline = env.make_offline

    def build(*, rates, latencies, outputs=None):
        def with_latencies(**options):
            original_evidence = options["evidence"]
            def evidence(model, case):
                return RecordingEvidence.model_validate({
                    **original_evidence(model, case).model_dump(), "latency_ms": latencies.get(model),
                })
            return make_offline(**{**options, "evidence": evidence})
        env.make_offline = with_latencies
        sample = env.build_optimization(rates=rates, outputs=outputs)
        assert sample.job.plan.provenance == "test"
        assert all(item.provenance == "test" for item in sample.job.measurements)
        return sample.snapshot
    return build


def test_nearby_costs_and_faster_competitors_never_hide_the_cheapest_eligible_model(cost_selection_case):
    # Main's 86c6c86 fixes its 2% latency tie window. all-checks-then-cost.v1
    # has no such window: neither the baseline nor another candidate may hide
    # a cheaper model. Protect that existing behavior without porting the fix.
    snapshot = cost_selection_case(
        rates={"local/baseline": "1.00", "local/candidate": "0.99", "local/alternative": "0.995"},
        latencies={"local/baseline": 100.0, "local/candidate": 101.0, "local/alternative": 100.5},
    )
    result = optimize(snapshot)
    decision = result.decisions[0]
    candidates = {item.model.identifier: item for item in decision.candidates}
    assert result.provenance == decision.provenance == "test"
    assert all(item.eligibility == "eligible" for item in candidates.values())
    assert candidates["local/candidate"].latency_ms.mean == 101.0
    assert candidates["local/alternative"].latency_ms.mean == 100.5
    assert candidates["local/baseline"].latency_ms.mean == 100.0
    assert decision.status == "recommended" and decision.selected_model_id == "local/candidate"
    assert candidates["local/candidate"].cost_total_usd == Decimal("1.98")
    assert candidates["local/alternative"].cost_total_usd == Decimal("1.990")
    assert decision.recorded_savings_usd == Decimal("0.02")


@pytest.mark.parametrize("baseline_rate,selected,status,savings", [
    ("1.00", "local/baseline", "baseline_retained", Decimal("0")),
    ("2.00", "local/alternative", "recommended", Decimal("2.00")),
])
def test_equal_costs_follow_baseline_then_identifier_despite_latency_and_plan_order(
        cost_selection_case, baseline_rate, selected, status, savings):
    snapshot = cost_selection_case(
        rates={"local/baseline": baseline_rate, "local/candidate": "1.00", "local/alternative": "1.00"},
        latencies={"local/baseline": 101.0, "local/candidate": 100.0, "local/alternative": 102.0},
    )
    decision = optimize(snapshot).decisions[0]
    # The alphabetically first alternative is last in the plan and slowest.
    assert snapshot.job.plan.models[-1].identifier == "local/alternative"
    assert decision.selected_model_id == selected and decision.status == status
    assert decision.recorded_savings_usd == savings
    assert decision.candidates[1].cost_total_usd == decision.candidates[2].cost_total_usd == Decimal("2.00")


@pytest.mark.parametrize("missing", ["local/baseline", "local/candidate", "all"])
def test_missing_latency_cannot_disqualify_or_reprice_a_cheaper_eligible_model(cost_selection_case, missing):
    latencies = {"local/baseline": 100.0, "local/candidate": 101.0, "local/alternative": 100.5}
    latencies = {} if missing == "all" else {model: value for model, value in latencies.items() if model != missing}
    snapshot = cost_selection_case(
        rates={"local/baseline": "1.00", "local/candidate": "0.99", "local/alternative": "0.995"},
        latencies=latencies,
    )
    decision = optimize(snapshot).decisions[0]
    assert decision.status == "recommended" and decision.selected_model_id == "local/candidate"
    assert decision.recorded_savings_usd == Decimal("0.02")
    for candidate in decision.candidates:
        if missing == "all" or candidate.model.identifier == missing:
            assert candidate.latency_ms.availability == "unavailable"
            assert candidate.latency_ms.sample_count == 0 and candidate.latency_ms.mean is None
            assert candidate.eligibility == "eligible"


@pytest.mark.parametrize("missing", ["local/baseline", "local/candidate", "local/alternative"])
def test_available_latency_never_fills_a_missing_cost_or_proves_a_minimum(cost_selection_case, missing):
    rates = {"local/baseline": "1.00", "local/candidate": "0.99", "local/alternative": "0.995", missing: None}
    snapshot = cost_selection_case(rates=rates,
        latencies={"local/baseline": 100.0, "local/candidate": 101.0, "local/alternative": 100.5})
    decision = optimize(snapshot).decisions[0]
    candidate = next(item for item in decision.candidates if item.model.identifier == missing)
    assert candidate.latency_ms.availability == "available" and candidate.quality_pass_rate == Decimal("1")
    assert candidate.eligibility == "insufficient" and candidate.cost_total_usd is None
    assert candidate.reasons == ("cost_unavailable",)
    assert decision.status == "inconclusive" and decision.selected_model_id is None
    assert decision.recorded_savings_usd is None
    assert decision.reason == ("baseline_ineligible" if missing == "local/baseline" else "candidate_evidence_incomplete")


def test_cheapest_fastest_candidate_cannot_win_with_failed_required_checks(cost_selection_case):
    outputs = {(model, case): ("wrong-test-output" if model == "local/alternative" else expected)
               for model in ("local/baseline", "local/candidate", "local/alternative")
               for case, expected in (("case-one", "PRIVATE_CAPTURE_ONE"), ("case-two", "PRIVATE_CAPTURE_TWO"))}
    snapshot = cost_selection_case(
        rates={"local/baseline": "1.00", "local/candidate": "0.99", "local/alternative": "0"},
        latencies={"local/baseline": 100.0, "local/candidate": 101.0, "local/alternative": 1.0}, outputs=outputs,
    )
    decision = optimize(snapshot).decisions[0]
    rejected = next(item for item in decision.candidates if item.model.identifier == "local/alternative")
    assert rejected.cost_total_usd == Decimal("0") and rejected.latency_ms.mean == 1.0
    assert rejected.eligibility == "rejected" and "quality_failed" in rejected.reasons
    assert decision.status == "recommended" and decision.selected_model_id == "local/candidate"
    assert decision.recorded_savings_usd == Decimal("0.02")
