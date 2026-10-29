"""Evidence-only populations and exact decimal cost; no estimates or comparisons."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext

from backend.schemas import (
    BenchmarkMeasurement, BenchmarkPlan, CostCalculation, MetricPopulation, OfflineMetrics,
    PinnedPricing, RecordingEvidence, VersionedReference,
)


def calculate_cost(evidence: RecordingEvidence, pricing: PinnedPricing | None) -> CostCalculation:
    evidence = RecordingEvidence.model_validate(evidence)
    if evidence.input_tokens is None or evidence.output_tokens is None:
        return CostCalculation(availability="unavailable", reason="missing_usage")
    if pricing is None:
        return CostCalculation(availability="unavailable", reason="missing_pricing")
    pricing = PinnedPricing.model_validate(pricing)
    if evidence.pricing_reference != VersionedReference(identifier=pricing.identifier, version=pricing.version):
        return CostCalculation(availability="unavailable", reason="missing_pricing")
    if evidence.captured_at < pricing.effective_at:
        return CostCalculation(availability="unavailable", reason="pricing_not_effective")
    with localcontext() as context:
        context.prec = 80
        amount = (Decimal(evidence.input_tokens) * pricing.input_usd_per_million
                  + Decimal(evidence.output_tokens) * pricing.output_usd_per_million) / Decimal(1000000)
    return CostCalculation(availability="available", amount_usd=amount,
                           pricing_reference=evidence.pricing_reference, pricing_digest=pricing.digest)


def _latency(values):
    if not values:
        return MetricPopulation(availability="unavailable", unit="ms", sample_count=0, reason="empty_population")
    try:
        mean = values[0] if min(values) == max(values) else math.fsum(values) / len(values)
        if mean == 0 and any(value > 0 for value in values):
            raise ArithmeticError()
    except (ArithmeticError, OverflowError):
        return MetricPopulation(availability="unavailable", unit="ms", sample_count=len(values), reason="arithmetic_limit")
    return MetricPopulation(availability="available", unit="ms", sample_count=len(values),
                            minimum=min(values), maximum=max(values), mean=mean)


def _tokens(values):
    if not values:
        return MetricPopulation(availability="unavailable", unit="tokens", sample_count=0, reason="empty_population")
    total = sum(values)
    if total > 2**53 - 1:
        return MetricPopulation(availability="unavailable", unit="tokens", sample_count=len(values), reason="arithmetic_limit")
    return MetricPopulation(availability="available", unit="tokens", sample_count=len(values), total_tokens=total)


def aggregate(plan: BenchmarkPlan, measurements: tuple[BenchmarkMeasurement, ...]) -> OfflineMetrics:
    plan = BenchmarkPlan.model_validate(plan)
    if type(measurements) not in (list, tuple) or len(measurements) > 1024:
        raise ValueError("The aggregate input exceeds the unit budget.")
    records = tuple(BenchmarkMeasurement.model_validate(item) for item in measurements)
    if any(item.evaluation is None or item.recording_id is None or item.evidence_digest is None or item.output_available is None for item in records):
        raise ValueError("Offline aggregates require evaluated, integrity-identified records.")
    keys = [item.unit_key() for item in records]
    if len(keys) != len(set(keys)) or not set(keys) <= set(plan.unit_keys()) or any(item.provenance != plan.provenance for item in records):
        raise ValueError("Measurements do not belong to the plan.")
    counts = {name: 0 for name in ("passed", "failed", "skipped", "inconclusive", "not_run")}
    for item in records:
        counts["not_run" if item.evaluation_status == "unavailable" else item.evaluation_status] += 1
    costs = [item.calculated_cost.amount_usd for item in records
             if item.calculated_cost is not None and item.calculated_cost.availability == "available"]
    if costs:
        with localcontext() as context:
            context.prec = 80
            total = sum(costs, Decimal(0))
        cost_population = MetricPopulation(availability="available", unit="USD", sample_count=len(costs), total_usd=total)
    else:
        cost_population = MetricPopulation(availability="unavailable", unit="USD", sample_count=0, reason="empty_population")
    return OfflineMetrics(
        provenance=plan.provenance, planned_cases=len(plan.case_ids), planned_units=len(plan.unit_keys()),
        processed_units=len(records), valid_recorded_outputs=sum(item.output_available is True for item in records),
        evaluated_units=sum(item.evaluation is not None and bool(item.evaluation.checks_ran) for item in records),
        processing_complete=len(records) == len(plan.unit_keys()),
        evaluation_complete=counts["passed"] + counts["failed"] == len(plan.unit_keys()),
        latency_ms=_latency([item.latency_ms.value for item in records if item.latency_ms.availability == "available"]),
        ttft_ms=_latency([item.ttft_ms.value for item in records if item.ttft_ms is not None and item.ttft_ms.availability == "available"]),
        input_tokens=_tokens([item.input_tokens.value for item in records if item.input_tokens.availability == "available"]),
        output_tokens=_tokens([item.output_tokens.value for item in records if item.output_tokens.availability == "available"]),
        cost_usd=cost_population, **counts,
    )
