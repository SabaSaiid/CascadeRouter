"""Forgery tests use test captures only; no pretend genuine production dataset."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.compiler.metrics import aggregate
from backend.compiler.router_optimizer import optimize
from backend.schemas import BenchmarkSummary, JobResponse
from backend.services.errors import ServiceError
from backend.services.optimization import OptimizationService, verify_evidence


def register(env, sample):
    env.storage.register_benchmark_versions(sample.registry.version_records() + sample.executor.version_records())


def test_test_labels_or_a_claimed_approval_cannot_enable_production_optimization(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    scans = SimpleNamespace(storage=env.storage, access=env.access)
    jobs = SimpleNamespace(available=True, executor=sample.executor, registry=sample.registry)
    service = OptimizationService(env.settings, scans, jobs)
    assert not service.available and not sample.executor.production_approved
    assert not sample.registry.production_approved
    # An internal test snapshot may exercise arithmetic, but retains test provenance.
    result = optimize(replace(sample.snapshot, approval_manifest_digest="a" * 64, recording_dataset_digest="b" * 64))
    assert result.provenance == "test" and all(item.provenance == "test" for item in result.decisions)


def test_integrity_verification_matches_actual_test_captures_without_mutating_job(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    register(env, sample)
    original = env.storage.get_job(sample.job.run_id).model_dump_json()
    verify_evidence(sample.job, sample.registry, sample.executor, env.storage)
    assert env.storage.get_job(sample.job.run_id).model_dump_json() == original


@pytest.mark.parametrize("field", ["latency_ms", "calculated_cost", "evidence_digest", "evaluation"])
def test_structurally_valid_forged_measurements_cannot_drive_decisions(optimization_environment, field):
    env = optimization_environment
    sample = env.build_optimization()
    register(env, sample)
    data = sample.job.model_dump()
    record = data["measurements"][0]
    if field == "latency_ms":
        record[field] = {"availability": "available", "value": 1.0}
    elif field == "calculated_cost":
        record[field]["amount_usd"] = Decimal("0")
    elif field == "evidence_digest":
        record[field] = "0" * 64
    else:
        record[field] = {"status": "failed", "reason": "mismatch", "checks_ran": ("exact",), "validation_status": "failed"}
        record["evaluation_status"] = "failed"
    # Recompute a structurally consistent summary; only capture revalidation can
    # detect this class of forgery. This remains synthetic test evidence.
    from backend.schemas import BenchmarkMeasurement
    measurements = tuple(BenchmarkMeasurement.model_validate(item) for item in data["measurements"])
    data["measurements"] = measurements
    data["result"] = BenchmarkSummary(provenance="test", evaluation_status="failed" if field == "evaluation" else "passed",
                                      metrics=aggregate(sample.job.plan, measurements))
    forged = JobResponse.model_validate(data)
    with pytest.raises(ServiceError) as error:
        verify_evidence(forged, sample.registry, sample.executor, env.storage)
    assert error.value.code == "source_conflict"


def test_missing_version_registration_cannot_be_silently_created(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    with pytest.raises(ServiceError):
        verify_evidence(sample.job, sample.registry, sample.executor, env.storage)
    with pytest.raises(ServiceError):
        env.storage.verify_benchmark_versions(sample.registry.version_records())


@pytest.mark.parametrize("field", ["analysis_digest", "case_set_digest", "evaluation_profile_digest", "execution_digest", "registry_digest"])
def test_stale_plan_identity_cannot_be_combined_with_current_evidence(optimization_environment, field):
    env = optimization_environment
    sample = env.build_optimization()
    register(env, sample)
    data = sample.job.model_dump()
    data["plan"][field] = "0" * 64
    stale = JobResponse.model_validate(data)
    with pytest.raises(ServiceError):
        verify_evidence(stale, sample.registry, sample.executor, env.storage)


def test_read_only_version_verification_rejects_conflicts_without_overwriting(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    register(env, sample)
    original = sample.registry.version_records()
    first = original[0]
    changed = ((first[0], first[1], first[2], "0" * 64, first[4]),)
    with pytest.raises(ServiceError):
        env.storage.verify_benchmark_versions(changed)
    env.storage.verify_benchmark_versions(original)


def test_changed_model_version_is_rejected_even_with_same_model_identifier(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    register(env, sample)
    data = sample.job.model_dump()
    data["plan"]["models"][1]["version"] = "v2"
    with pytest.raises(ServiceError):
        verify_evidence(JobResponse.model_validate(data), sample.registry, sample.executor, env.storage)


def test_corrupt_or_changed_approved_test_asset_is_rejected(asset_environment):
    import threading
    from datetime import datetime, timezone
    from backend.schemas import BenchmarkSummary
    from backend.services.benchmark_cases import load_local_assets
    env = asset_environment
    registry, executor = load_local_assets(env.settings, allow_test_assets=True)
    plan = registry.resolve(env.request, env.analysis, env.settings, executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    env.storage.transition_job(job.run_id, ("queued",), status="running")
    records = tuple(executor.execute(plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc)))
    for item in records:
        env.storage.transition_job(job.run_id, ("running",), measurement=item)
    job = env.storage.transition_job(job.run_id, ("running",), status="complete",
        result=BenchmarkSummary(provenance="test", evaluation_status="passed", metrics=aggregate(plan, records)))
    env.storage.register_benchmark_versions(registry.version_records() + executor.version_records())
    env.recording_path.write_bytes(env.recording_path.read_bytes() + b" ")
    with pytest.raises(ServiceError):
        verify_evidence(job, registry, executor, env.storage)
