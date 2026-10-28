"""Arithmetic fixtures are test evidence, not model performance measurements."""

import threading
from datetime import datetime, timezone
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from backend.compiler.metrics import aggregate, calculate_cost
from backend.schemas import LocalBenchmarkCase, RecordingEvidence, VersionedReference


def measurements(env, registry=None, executor=None):
    registry, executor = registry or env.registry, executor or env.executor
    plan = registry.resolve(env.request, env.analysis, env.settings, executor)
    records = tuple(executor.execute(plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc)))
    return plan, records


def test_empty_populations_and_missing_financial_evidence_stay_null(offline_environment):
    env = offline_environment
    plan, records = measurements(env)
    result = aggregate(plan, records)
    assert result.planned_cases == 2 and result.planned_units == result.processed_units == 4
    assert result.passed == result.evaluated_units == result.valid_recorded_outputs == 4
    for population in (result.latency_ms, result.ttft_ms, result.input_tokens, result.output_tokens, result.cost_usd):
        assert population.availability == "unavailable" and population.sample_count == 0
        assert population.mean is None and population.total_tokens is None and population.total_usd is None
    for item in records:
        assert item.calculated_cost.amount_usd is None and item.calculated_cost.reason == "missing_usage"
    assert result.model_dump_json() == aggregate(plan, records).model_dump_json()
    empty = aggregate(plan, ())
    assert not empty.processing_complete and empty.processed_units == 0
    assert empty.passed == 0 and empty.latency_ms.mean is None


def test_populations_count_only_observed_values_and_ttft_is_not_derived(offline_environment):
    env = offline_environment
    def evidence(model, case):
        return RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z",
                                 latency_ms=10.0 if case == "case-one" else None,
                                 input_tokens=3 if case == "case-one" else None, output_tokens=None)
    registry, _, executor = env.make_offline(evidence=evidence)
    plan, records = measurements(env, registry, executor)
    result = aggregate(plan, records)
    assert result.latency_ms.sample_count == 2 and result.latency_ms.mean == 10.0
    assert result.input_tokens.sample_count == 2 and result.input_tokens.total_tokens == 6
    assert result.output_tokens.total_tokens is None and result.ttft_ms.mean is None
    assert result.cost_usd.total_usd is None


def test_decimal_calculation_uses_pinned_usage_and_pricing_without_float_rounding(offline_environment):
    env = offline_environment
    price = env.price(input_usd_per_million="0.100000000001", output_usd_per_million="0.200000000002")
    evidence = RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z", input_tokens=1, output_tokens=1,
                                 pricing_reference=VersionedReference(identifier=price.identifier, version=price.version))
    with localcontext() as context:
        context.prec = 2
        result = calculate_cost(evidence, price)
        assert context.prec == 2
    assert result.amount_usd == Decimal("0.000000300000000003")
    assert '"0.000000300000000003"' in result.model_dump_json()
    no_usage = RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z")
    assert calculate_cost(no_usage, price).amount_usd is None
    assert calculate_cost(evidence, None).reason == "missing_pricing"
    earlier = RecordingEvidence.model_validate({**evidence.model_dump(), "captured_at": "2010-01-01T00:00:00Z"})
    assert calculate_cost(earlier, price).reason == "pricing_not_effective"
    for change in ({"input_usd_per_million": 0.1}, {"digest": "0" * 64}):
        with pytest.raises(ValidationError):
            type(price).model_validate({**price.model_dump(), **change})


def test_aggregate_decimal_cost_and_streaming_populations(offline_environment):
    env = offline_environment
    prices = tuple(env.price(model.identifier) for model in env.registry.document.models)
    price_map = {price.model_id: price for price in prices}
    def evidence(model, case):
        price = price_map[model]
        return RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z", input_tokens=1000000,
            output_tokens=2000000, latency_ms=20.0, streaming=True, ttft_ms=2.0,
            pricing_reference=VersionedReference(identifier=price.identifier, version=price.version))
    registry, _, executor = env.make_offline(evidence=evidence, prices=prices)
    plan, records = measurements(env, registry, executor)
    result = aggregate(plan, records)
    assert result.cost_usd.total_usd == Decimal("2.00") and result.cost_usd.sample_count == 4
    assert result.ttft_ms.sample_count == 4 and result.ttft_ms.mean == 2.0
    assert all(item.cost_usd.value is None for item in records)  # Decimal field carries the calculation.
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_skipped_and_unrun_cases_never_enter_pass_counts(offline_environment):
    env = offline_environment
    cases = [LocalBenchmarkCase(identifier="one", input_text="test", expected_output="a"),
             LocalBenchmarkCase(identifier="two", input_text="test", expected_output="b", skip_reason="operator_excluded"),
             LocalBenchmarkCase(identifier="three", input_text="test", expected_output="c")]
    outputs = {(model.identifier, case.identifier): case.expected_output for model in env.registry.document.models for case in cases[:2]}
    registry, _, executor = env.make_offline(cases=cases, outputs=outputs)
    plan, records = measurements(env, registry, executor)
    result = aggregate(plan, records)
    assert result.passed == 2 and result.skipped == 2 and result.not_run == 2 and result.evaluated_units == 2
    assert result.processing_complete and not result.evaluation_complete
    assert not aggregate(plan, records[:1]).processing_complete


def test_unrepresentable_token_total_is_unavailable_with_actual_sample_count(offline_environment):
    env = offline_environment
    def evidence(model, case):
        return RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z", input_tokens=2**53 - 1)
    registry, _, executor = env.make_offline(evidence=evidence)
    plan, records = measurements(env, registry, executor)
    result = aggregate(plan, records)
    assert result.input_tokens.sample_count == 4 and result.input_tokens.total_tokens is None
    assert result.input_tokens.reason == "arithmetic_limit"


def test_ttft_requires_explicit_streaming_evidence():
    for values in ({"streaming": False, "ttft_ms": 1.0}, {"streaming": True, "latency_ms": 1.0, "ttft_ms": 2.0}):
        with pytest.raises(ValidationError):
            RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z", **values)


def test_observed_zero_is_distinct_from_missing_data(offline_environment):
    env = offline_environment
    def evidence(model, case):
        return RecordingEvidence(source_id="test-trace", captured_at="2026-10-28T00:00:00Z", input_tokens=0, latency_ms=0.0)
    registry, _, executor = env.make_offline(evidence=evidence)
    plan, records = measurements(env, registry, executor)
    result = aggregate(plan, records)
    assert result.latency_ms.availability == "available" and result.latency_ms.mean == 0.0
    assert result.input_tokens.availability == "available" and result.input_tokens.total_tokens == 0
    assert result.output_tokens.availability == "unavailable" and result.output_tokens.total_tokens is None


def test_offline_iteration_checks_cancellation_and_deadline_between_units(offline_environment):
    env = offline_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    cancellation = threading.Event()
    future = datetime.max.replace(tzinfo=timezone.utc)
    iterator = env.executor.execute(plan, cancellation, future)
    assert next(iterator).evaluation.status == "passed"
    cancellation.set()
    assert tuple(iterator) == ()
    assert tuple(env.executor.execute(plan, threading.Event(), datetime.min.replace(tzinfo=timezone.utc))) == ()


def test_bare_legacy_status_flags_cannot_become_offline_evaluation_evidence(offline_environment):
    env = offline_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    legacy = env.measurement(plan.unit_keys()[0], evaluation_status="passed")
    with pytest.raises(ValueError):
        aggregate(plan, (legacy,))
