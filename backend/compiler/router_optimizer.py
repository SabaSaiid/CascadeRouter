"""Pure bounded decisions over a verified snapshot; no inference or asset loading.

The service authenticates evidence before constructing this internal snapshot.
Unit tests may exercise the same algorithm with test provenance; that never
authorizes the production API or changes test evidence into recorded evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from backend.compiler.metrics import _latency
from backend.schemas import (
    JobResponse, OptimizationCandidate, OptimizationResult, RoutingDecision,
    content_digest, optimization_threshold,
)


@dataclass(frozen=True)
class OptimizationSnapshot:
    job: JobResponse
    quality_threshold: Decimal | None
    configuration_digest: str
    approval_manifest_digest: str | None = None
    recording_dataset_digest: str | None = None


def _measurement_digest(records):
    data = [item.model_dump(mode="json") for item in sorted(records, key=lambda item: item.unit_key())]
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _candidate(model, records, plan, threshold):
    records = tuple(records)
    planned = len(plan.case_ids)
    verified = tuple(item for item in records if item.evaluation is not None
                     and item.recording_id is not None and item.evidence_digest is not None and item.output_available is True)
    passed = sum(item.evaluation.status == "passed" and bool(item.evaluation.checks_ran)
                 and item.evaluation.validation_status == "passed" for item in verified)
    failed = sum(item.evaluation.status == "failed" for item in verified)
    unresolved = planned - passed - failed
    rate = None
    with localcontext() as context:
        context.prec = 80
        if unresolved == 0:
            rate = (Decimal(passed) / planned).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        costed = [item.calculated_cost.amount_usd for item in verified
                  if item.calculated_cost is not None and item.calculated_cost.availability == "available"
                  and item.input_tokens.availability == item.output_tokens.availability == "available"]
        cost = sum(costed, Decimal(0)) if len(costed) == planned else None
    reasons = []
    if failed:
        reasons.append("quality_failed")
    if unresolved:
        reasons.append("quality_unavailable")
    if rate is not None and rate < threshold:
        reasons.append("threshold_not_met")
    if cost is None:
        reasons.append("cost_unavailable")
    eligibility = "rejected" if failed else "insufficient" if reasons else "eligible"
    return OptimizationCandidate(
        model=model, provenance=plan.provenance, eligibility=eligibility, reasons=reasons,
        planned_cases=planned, passed_cases=passed, failed_cases=failed, unresolved_cases=unresolved,
        quality_pass_rate=rate, cost_total_usd=cost,
        latency_ms=_latency([item.latency_ms.value for item in verified if item.latency_ms.availability == "available"]),
        measurement_digest=_measurement_digest(records) if records else None,
    )


def _result(snapshot, decisions, diagnostics=()):
    job, plan = snapshot.job, snapshot.job.plan
    counts = {state: sum(item.status == state for item in decisions)
              for state in ("recommended", "baseline_retained", "inconclusive", "unavailable")}
    complete = counts["recommended"] + counts["baseline_retained"] == len(decisions)
    return OptimizationResult(
        configuration_digest=snapshot.configuration_digest, run_id=job.run_id, benchmark_digest=content_digest(job), plan=plan,
        approval_manifest_digest=snapshot.approval_manifest_digest, recording_dataset_digest=snapshot.recording_dataset_digest,
        quality_threshold=snapshot.quality_threshold, provenance=plan.provenance, decisions=decisions,
        status="complete" if complete else "unavailable" if counts["unavailable"] == len(decisions) else "inconclusive",
        nodes_considered=len(decisions), nodes_eligible=sum(any(item.eligibility == "eligible" for item in decision.candidates) for decision in decisions),
        nodes_recommended=counts["recommended"], nodes_retained=counts["baseline_retained"],
        nodes_inconclusive=counts["inconclusive"], nodes_unavailable=counts["unavailable"],
        decisions_complete=complete, diagnostics=diagnostics,
    )


def unavailable(snapshot: OptimizationSnapshot, reason) -> OptimizationResult:
    job = JobResponse.model_validate(snapshot.job)
    decisions = tuple(RoutingDecision(
        analysis_id=job.plan.analysis_id, node_id=node, provenance=job.plan.provenance,
        status="unavailable", reason=reason, baseline_model_id=job.plan.models[0].identifier,
        quality_threshold=snapshot.quality_threshold, candidates=(),
    ) for node in sorted(job.plan.node_ids))
    return _result(snapshot, decisions, (reason,))


def optimize(snapshot: OptimizationSnapshot, check=lambda: None) -> OptimizationResult:
    """Strict required checks, then minimum comparable total recorded USD cost.

    A pass fraction describes only these cases, not a general model quality
    score. All required checks must pass even if a configured threshold is lower.
    Missing candidate evidence prevents claiming a minimum over the whole plan.
    Ties retain the baseline; other equal minima sort by model identifier.
    """
    job = JobResponse.model_validate(snapshot.job)
    if snapshot.quality_threshold is None:
        return unavailable(snapshot, "threshold_unconfigured")
    threshold = optimization_threshold(snapshot.quality_threshold)
    if job.status != "complete":
        return unavailable(snapshot, "benchmark_incomplete")
    if job.plan.provenance == "recorded" and (snapshot.approval_manifest_digest is None or snapshot.recording_dataset_digest is None):
        return unavailable(snapshot, "approval_unavailable")
    check()
    by_node_model = {}
    for item in job.measurements:
        by_node_model.setdefault((item.node_id, item.model_id), []).append(item)
    decisions = []
    for node in sorted(job.plan.node_ids):
        candidates = []
        for model in job.plan.models:
            check()
            candidates.append(_candidate(model, by_node_model.get((node, model.identifier), ()), job.plan, threshold))
        baseline = candidates[0]
        selected = None
        if baseline.eligibility != "eligible":
            status, reason = "inconclusive", "baseline_ineligible"
        elif any(item.eligibility == "insufficient" for item in candidates[1:]):
            status, reason = "inconclusive", "candidate_evidence_incomplete"
        else:
            selected = min((item for item in candidates if item.eligibility == "eligible"),
                           key=lambda item: (item.cost_total_usd, item.model != baseline.model, item.model.identifier))
            if selected == baseline:
                status = "baseline_retained"
                reason = "no_eligible_alternative" if all(item.eligibility == "rejected" for item in candidates[1:]) else "baseline_lowest_cost"
            else:
                status, reason = "recommended", "lowest_recorded_cost"
        with localcontext() as context:
            context.prec = 80
            saving = None if selected is None else baseline.cost_total_usd - selected.cost_total_usd
        decisions.append(RoutingDecision(
            analysis_id=job.plan.analysis_id, node_id=node, provenance=job.plan.provenance, status=status, reason=reason,
            baseline_model_id=baseline.model.identifier, selected_model_id=None if selected is None else selected.model.identifier,
            differs_from_baseline=selected is not None and selected != baseline, quality_threshold=threshold,
            candidates=candidates, recorded_savings_usd=saving,
        ))
    check()
    return _result(snapshot, decisions)
