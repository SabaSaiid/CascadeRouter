"""Lifecycle, durable transitions and races with deterministic test-only work."""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import BackendConfig
from backend.schemas import BenchmarkRequest, JobResponse, TERMINAL_JOB_STATES
from backend.services import storage as storage_module
from backend.services.errors import ServiceError
from backend.services.jobs import JobService
from backend.services.storage import AnalysisStorage, _DDL_V1


@contextmanager
def running(env, **changes):
    executor = changes.get("executor", env.executor)
    service = JobService(changes.pop("settings", env.settings), env.storage, env.access,
                         registry=changes.pop("registry", env.registry),
                         executor=changes.pop("executor", env.executor), allow_test_executor=True, **changes)
    try:
        yield service
    finally:
        env.executor.release.set()
        if hasattr(executor, "release"):
            executor.release.set()
        service.close()


def wait_for(service, run_id, predicate=lambda job: job.status in TERMINAL_JOB_STATES, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = service.get(run_id)
        if predicate(job):
            return job
        time.sleep(0.01)
    pytest.fail("Job did not reach the expected state.")


def keyed(env, key):
    return BenchmarkRequest.model_validate({**env.request.model_dump(), "idempotency_key": key})


def test_persistent_execution_complete_keeps_measurements_unavailable(job_environment):
    env = job_environment
    with running(env) as service:
        accepted = service.submit(env.request)
        assert accepted.status == "queued" and accepted.provenance == "test"
        job = wait_for(service, accepted.run_id)
        assert job.status == "complete" and env.executor.finished.is_set()
        assert job.progress.completed_units == job.progress.total_units == 4
        assert job.result.evaluation_status == "inconclusive"
        assert all(item.latency_ms.value is None and item.input_tokens.value is None and item.output_tokens.value is None
                   and item.cost_usd.value is None and item.quality_score is None for item in job.measurements)
        assert JobResponse.model_validate_json(job.model_dump_json()) == job
        assert "PRIVATE_" not in job.model_dump_json()
        assert service.cancel(job.run_id) == job
    assert b"PRIVATE_LOCAL_CASE_INPUT" not in (env.directory / "analyses.sqlite3").read_bytes()


def test_quality_failure_does_not_mean_execution_failure(job_environment):
    env = job_environment
    env.executor.evaluation_status = "failed"
    with running(env) as service:
        job = wait_for(service, service.submit(env.request).run_id)
        assert job.status == "complete" and job.result.evaluation_status == "failed"


def test_executor_failure_is_sanitized_and_persisted(job_environment, caplog):
    env = job_environment
    env.executor.failure = True
    with running(env) as service:
        job = wait_for(service, service.submit(env.request).run_id)
        assert job.status == "error" and job.error.code == "executor_failed"
        assert job.result is None and job.progress.completed_units == 0
        assert "PRIVATE_EXECUTOR_EXCEPTION" not in job.model_dump_json() + caplog.text


def test_sql_and_service_reject_invalid_transitions_and_plan_updates(job_environment):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    with pytest.raises(ServiceError):
        env.storage.transition_job(job.run_id, ("queued",), status="complete")
    env.storage.transition_job(job.run_id, ("queued",), status="running")
    with pytest.raises(ServiceError):
        env.storage.transition_job(job.run_id, ("running",), status="queued")
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        for sql, values in (("UPDATE jobs SET plan_payload = ? WHERE run_id = ?", (b"changed", job.run_id)),
                            ("UPDATE jobs SET status = ? WHERE run_id = ?", ("queued", job.run_id))):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql, values)
    env.storage.transition_job(job.run_id, ("running",), status="error", error_code="executor_failed")
    with pytest.raises(ServiceError):
        env.storage.transition_job(job.run_id, ("error",), status="running")


def test_queue_saturation_rolls_back_job_and_key_and_queued_cancel_releases_slot(job_environment):
    env = job_environment
    env.executor.release.clear()
    with running(env) as service:
        first = service.submit(env.request)
        assert env.executor.started.wait(5)
        second, third = service.submit(env.request), service.submit(env.request)
        with pytest.raises(ServiceError) as error:
            service.submit(keyed(env, "retry-after-capacity"))
        assert error.value.code == "capacity_exceeded"
        with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3
        cancelled = service.cancel(second.run_id)
        assert cancelled.status == "cancelled" and cancelled.progress.completed_units == 0
        assert service.cancel(second.run_id) == cancelled
        retry = service.submit(keyed(env, "retry-after-capacity"))
        env.executor.release.set()
        assert wait_for(service, first.run_id).status == "complete"
        assert wait_for(service, third.run_id).status == "complete"
        assert wait_for(service, retry.run_id).status == "complete"
        assert len(env.executor.calls) == 3


def test_idempotent_concurrent_retry_executes_once_and_conflicting_key_rejected(job_environment):
    env = job_environment
    with running(env) as service:
        request = keyed(env, "same-request")
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(lambda _: service.submit(request), range(8)))
        assert len({item.run_id for item in accepted}) == 1
        assert wait_for(service, accepted[0].run_id).status == "complete"
        assert len(env.executor.calls) == 1
        changed = BenchmarkRequest.model_validate({**request.model_dump(), "node_ids": [env.analysis.nodes[1].node_id]})
        with pytest.raises(ServiceError) as error:
            service.submit(changed)
        assert error.value.code == "source_conflict"


def test_concurrent_creation_and_retained_job_limit(job_environment):
    env = job_environment
    settings = BackendConfig(permitted_repository_roots=env.settings.permitted_repository_roots, storage_directory=env.directory,
                             job_workers=2, max_queued_jobs=16, max_jobs=16)
    with running(env, settings=settings) as service:
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(lambda index: service.submit(keyed(env, f"concurrent-{index}")), range(16)))
        for item in accepted:
            assert wait_for(service, item.run_id).status == "complete"
        assert len({item.run_id for item in accepted}) == 16
        with pytest.raises(ServiceError) as error:
            service.submit(env.request)
        assert error.value.code == "capacity_exceeded"


@pytest.mark.parametrize("cooperative", [True, False])
def test_running_cancellation_is_not_worker_termination(job_environment, cooperative):
    env = job_environment
    env.executor.release.clear()
    env.executor.cooperative = cooperative
    with running(env) as service:
        run_id = service.submit(env.request).run_id
        assert env.executor.started.wait(5)
        assert service.cancel(run_id).status == "cancelling"
        if not cooperative:
            assert not env.executor.finished.is_set()
            assert service.get(run_id).status == service.cancel(run_id).status == "cancelling"
            assert run_id in service.active
            env.executor.release.set()
        job = wait_for(service, run_id)
        assert env.executor.finished.is_set() and job.status == "cancelled" and job.result is None


def test_completion_cleanup_race_waits_before_cancelled(job_environment):
    env = job_environment
    cleanup_entered, cleanup_release = threading.Event(), threading.Event()
    original = env.executor.execute

    def execute(*args):
        try:
            yield from original(*args)
        finally:
            cleanup_entered.set()
            assert cleanup_release.wait(5)

    env.executor.execute = execute
    with running(env) as service:
        try:
            run_id = service.submit(env.request).run_id
            assert cleanup_entered.wait(5)
            before = service.get(run_id)
            assert before.status == "running" and before.progress.completed_units == before.progress.total_units
            assert before.result is None
            assert service.cancel(run_id).status == "cancelling"
            assert service.get(run_id).status == "cancelling"
        finally:
            cleanup_release.set()
        assert wait_for(service, run_id).status == "cancelled"


def test_deadlines_do_not_release_noncooperative_worker_and_expire_queue(job_environment):
    env = job_environment
    settings = BackendConfig(permitted_repository_roots=env.settings.permitted_repository_roots, storage_directory=env.directory,
                             job_workers=1, max_queued_jobs=2, job_timeout_seconds=1, provider_timeout_seconds=1)
    # The shared store owns the accepted-job deadline configuration.
    env.storage.job_timeout_seconds = 1
    env.executor.release.clear()
    env.executor.cooperative = False
    with running(env, settings=settings) as service:
        first = service.submit(env.request).run_id
        assert env.executor.started.wait(5)
        queued = service.submit(env.request).run_id
        wait_for(service, first, lambda job: job.status == "cancelling")
        assert service.get(first).cancellation_reason == "deadline" and not env.executor.finished.is_set()
        assert wait_for(service, queued).status == "error"
        assert service.get(queued).progress.completed_units == 0
        env.executor.release.set()
        job = wait_for(service, first)
        assert job.status == "error" and job.error.code == "deadline_exceeded" and job.result is None


@pytest.mark.parametrize("initial", ["queued", "running", "cancelling"])
def test_restart_resumes_only_safe_queued_jobs_and_interrupts_in_progress(job_environment, initial):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    if initial != "queued":
        env.storage.transition_job(job.run_id, ("queued",), status="running")
    if initial == "cancelling":
        env.storage.transition_job(job.run_id, ("running",), status="cancelling", cancellation_reason="requested")
    with running(env) as service:
        actual = wait_for(service, job.run_id)
        assert actual.status == ("complete" if initial == "queued" else "interrupted")
        assert len(env.executor.calls) == (1 if initial == "queued" else 0)


@pytest.mark.parametrize("reason", ["missing_executor", "not_idempotent", "changed_executor", "changed_configuration"])
def test_unrecoverable_queued_plan_is_interrupted(job_environment, reason):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    changes = {}
    if reason == "missing_executor":
        changes["executor"] = None
    elif reason == "not_idempotent":
        env.executor.idempotent = False
    elif reason == "changed_executor":
        env.executor.identity = "f" * 64
    else:
        changes["settings"] = BackendConfig(permitted_repository_roots=env.settings.permitted_repository_roots,
                                            storage_directory=env.directory, job_timeout_seconds=301)
    with running(env, **changes) as service:
        actual = service.get(job.run_id)
        assert actual.status == "interrupted" and actual.error.code == "recovery_unavailable"
        assert not env.executor.calls


def test_exclusive_lease_prevents_recovery_race_and_duplicate_execution(job_environment):
    env = job_environment
    env.executor.release.clear()
    with running(env) as service:
        run_id = service.submit(env.request).run_id
        assert env.executor.started.wait(5)
        with pytest.raises(ServiceError) as error:
            JobService(env.settings, env.storage, env.access, registry=env.registry, executor=env.executor, allow_test_executor=True)
        assert error.value.code == "capability_unavailable"
        assert service.get(run_id).status == "running"
        env.executor.release.set()
        assert wait_for(service, run_id).status == "complete" and len(env.executor.calls) == 1


def test_oversized_or_duplicate_results_are_errors_with_bounded_progress(job_environment):
    env = job_environment
    env.storage.max_result_bytes = 1024
    with running(env) as service:
        job = wait_for(service, service.submit(env.request).run_id)
        assert job.status == "error" and job.error.code == "invalid_result" and job.result is None
        assert job.progress.completed_units < job.progress.total_units
        assert len(job.model_dump_json(include={"measurements"}).encode("utf-8")) <= 1024


def test_completion_write_failure_never_claims_complete(job_environment, monkeypatch):
    env = job_environment
    original = env.storage.transition_job

    def fail(*args, **kwargs):
        if kwargs.get("status") == "complete":
            raise ServiceError("capability_unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(env.storage, "transition_job", fail)
    with running(env) as service:
        job = wait_for(service, service.submit(env.request).run_id)
        assert job.status == "error" and job.error.code == "storage_unavailable" and job.result is None
        assert not service.available


def test_v1_database_migration_preserves_analysis_and_is_repeatable(api_environment):
    settings, repository, directory = api_environment
    from backend.services.compiler_adapter import analyze_for_api
    analysis = analyze_for_api(str(repository), analysis_id="analysis_" + "d" * 32, timestamp=datetime.now(timezone.utc))
    path = directory / "analyses.sqlite3"
    with sqlite3.connect(path) as connection:
        for ddl in _DDL_V1:
            connection.execute(ddl)
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
                           (analysis.analysis_id, analysis.model_dump(mode="json")["timestamp"], analysis.schema_version,
                            "complete", analysis.model_dump_json().encode("utf-8")))
    for _ in range(2):
        storage = AnalysisStorage(settings)
        assert storage.get(analysis.analysis_id) == analysis
        storage.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_failed_migration_rolls_back_schema_atomically(api_environment, monkeypatch):
    settings, _, directory = api_environment
    path = directory / "analyses.sqlite3"
    with sqlite3.connect(path) as connection:
        for ddl in _DDL_V1:
            connection.execute(ddl)
        connection.execute("PRAGMA user_version = 1")
    with monkeypatch.context() as scoped:
        scoped.setattr(storage_module, "_DDL", (*storage_module._DDL, "INVALID MIGRATION STATEMENT"))
        with pytest.raises(ServiceError):
            AnalysisStorage(settings)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", ("jobs",)).fetchone()[0] == 0
    storage = AnalysisStorage(settings)
    storage.close()


def test_expired_recovery_and_queue_submission_failure_are_not_orphans(job_environment, monkeypatch):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)

    def failed_enqueue(_):
        raise ServiceError("capacity_exceeded")

    with pytest.raises(ServiceError):
        env.storage.create_job(keyed(env, "rollback-key"), plan, failed_enqueue)
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    class PastDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) - timedelta(hours=1)

    with monkeypatch.context() as scoped:
        scoped.setattr(storage_module, "datetime", PastDatetime)
        expired = env.storage.create_job(env.request, plan, lambda _: None)
    with running(env) as service:
        job = service.get(expired.run_id)
        assert job.status == "error" and job.error.code == "deadline_exceeded"
        assert not env.executor.calls


def test_duplicate_progress_cannot_create_a_false_completed_result(job_environment):
    env = job_environment

    def duplicate(plan, cancellation, deadline):
        item = env.measurement(plan.unit_keys()[0])
        yield item
        yield item

    env.executor.execute = duplicate
    with running(env) as service:
        job = wait_for(service, service.submit(env.request).run_id)
        assert job.status == "error" and job.error.code == "invalid_result"
        assert job.progress.completed_units == 1 and job.result is None


@pytest.mark.parametrize("changes", [{"max_benchmark_units": 0}, {"max_benchmark_units": 1025},
                                     {"max_job_result_bytes": True}, {"max_job_result_bytes": 1023},
                                     {"max_job_result_bytes": 8 * 1024 * 1024 + 1}])
def test_new_job_limits_are_strict_and_bounded(changes):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        BackendConfig(**changes)
