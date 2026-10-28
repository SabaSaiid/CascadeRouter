"""Authenticate retained offline evidence, then perform bounded pure optimization."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from backend.compiler.metrics import aggregate
from backend.compiler.policy_generator import generate_policy
from backend.compiler.router_optimizer import OptimizationSnapshot, optimize, unavailable
from backend.schemas import OptimizationRequest, OptimizationResponse, content_digest
from .benchmark_cases import BenchmarkRegistry, digest
from .errors import ServiceError
from .offline_benchmark import OfflineBenchmarkExecutor


def verify_evidence(job, registry, executor, storage, check=lambda: None):
    """Integrity validation is independent of authorization; service gates it first.

    Re-evaluate captured data using the existing offline executor, never a target
    application. This detects forged per-case flags, costs and aggregate values
    even if the retained JSON still satisfies its structural schema.
    """
    if BenchmarkRegistry(registry.document).identity != registry.identity:
        raise ServiceError("source_conflict")
    fresh = OfflineBenchmarkExecutor(registry, executor.document, assets=executor.assets)
    if fresh.identity != executor.identity:
        raise ServiceError("source_conflict")
    if tuple(next((model for model in registry.document.models if model.identifier == planned.identifier), None)
             for planned in job.plan.models) != job.plan.models:
        raise ServiceError("source_conflict")
    check()
    fresh.validate_plan(job.plan)
    storage.verify_benchmark_versions(registry.version_records() + fresh.version_records())
    retained = {item.unit_key(): item for item in job.measurements}
    actual = []
    # Historic jobs have elapsed deadlines. The current HTTP check, rather than
    # the original execution deadline, bounds this read-only verification.
    for item in fresh.execute(job.plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc)):
        check()
        if retained.get(item.unit_key()) != item:
            raise ServiceError("source_conflict")
        actual.append(item)
    if len(actual) != len(retained) or job.result is None or aggregate(job.plan, tuple(actual)) != job.result.metrics:
        raise ServiceError("source_conflict")
    check()


class OptimizationService:
    def __init__(self, settings, scans, jobs):
        self.settings, self.scans, self.jobs = settings, scans, jobs
        self.configuration_digest = digest(("zero-cost.optimizer.v1:" + (
            "unconfigured" if settings.optimization_quality_threshold is None else format(settings.optimization_quality_threshold, "f")
        )).encode("ascii"))

    @property
    def available(self):
        return (self.settings.optimization_quality_threshold is not None and self.jobs is not None
                and self.jobs.available and type(self.jobs.executor) is OfflineBenchmarkExecutor
                and self.jobs.executor.production_approved and self.jobs.registry.production_approved)

    def optimize(self, request: OptimizationRequest, check=lambda: None) -> OptimizationResponse:
        request = OptimizationRequest.model_validate(request)
        storage = self.scans.storage
        analysis = storage.get(request.analysis_id)
        self.scans.access.select(analysis.repository_path)
        job = storage.get_job(request.run_id)
        plan = job.plan
        if (plan.analysis_id != analysis.analysis_id or not analysis.complete or analysis.data_source != "live"
                or plan.analysis_digest != digest(analysis.model_dump_json().encode("utf-8"))
                or not set(plan.node_ids) <= {node.node_id for node in analysis.nodes}
                or plan.case_set != request.case_set or plan.evaluation_profile != request.evaluation_profile):
            raise ServiceError("source_conflict")
        if len(plan.unit_keys()) > self.settings.max_benchmark_units:
            raise ServiceError("capacity_exceeded")
        snapshot = OptimizationSnapshot(job, self.settings.optimization_quality_threshold, self.configuration_digest)
        check()
        if plan.provenance == "test":
            result = unavailable(snapshot, "test_evidence")
        elif job.status != "complete":
            result = unavailable(snapshot, "benchmark_incomplete")
        elif self.settings.optimization_quality_threshold is None:
            result = unavailable(snapshot, "threshold_unconfigured")
        elif not self.available:
            result = unavailable(snapshot, "approval_unavailable")
        else:
            registry, executor = self.jobs.registry, self.jobs.executor
            verify_evidence(job, registry, executor, storage, check)
            snapshot = OptimizationSnapshot(
                job, self.settings.optimization_quality_threshold, self.configuration_digest,
                executor.assets.manifest_digest, content_digest(executor.document),
            )
            result = optimize(snapshot, check)
            # Changed/revoked approval during the decision must not issue a policy.
            executor.assets.verify()
        check()
        response = OptimizationResponse(result=result, policy=generate_policy(result))
        if len(response.model_dump_json().encode("utf-8")) > self.settings.max_job_result_bytes:
            raise ServiceError("capacity_exceeded")
        check()
        return response
