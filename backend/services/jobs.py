"""Persistent, zero-cost job lifecycle with a finite queue and fixed threads."""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.config import BackendConfig
from backend.schemas import (
    TERMINAL_JOB_STATES, BenchmarkMeasurement, BenchmarkRequest, BenchmarkSummary, JobAccepted, JobResponse,
)
from .benchmark_cases import BenchmarkExecutor, BenchmarkRegistry, ReplayExecutor
from .errors import ServiceError
from .repository_access import RepositoryAccess
from .storage import AnalysisStorage


class JobService:
    def __init__(self, settings: BackendConfig, storage: AnalysisStorage, access: RepositoryAccess, *,
                 registry: BenchmarkRegistry | None = None, executor: BenchmarkExecutor | None = None,
                 allow_test_executor: bool = False):
        self.settings, self.storage, self.access = settings, storage, access
        self.registry, self.executor = registry, executor
        self.condition = threading.Condition(threading.RLock())
        self.queue: deque[str] = deque()
        self.active: dict[str, threading.Event] = {}
        self.closing = False
        self.broken = False
        self.stopping = threading.Event()
        self.workers: list[threading.Thread] = []
        self.watchdog: threading.Thread | None = None
        self.enabled = bool(
            registry is not None and executor is not None
            and isinstance(executor.identity, str) and re.fullmatch(r"[0-9a-f]{64}", executor.identity)
            and ((allow_test_executor and executor.provenance == "test" and registry.document.origin == "test")
                 or (type(executor) is ReplayExecutor and executor.provenance == "recorded" and registry.document.origin == "local"))
        )
        self.lease = storage.job_lease()
        self.lease.__enter__()  # No recovery before exclusive ownership is established.
        try:
            self._recover()
            if self.enabled:
                for index in range(settings.job_workers):
                    worker = threading.Thread(target=self._worker, name=f"benchmark-local-{index}")
                    self.workers.append(worker)
                    worker.start()
                self.watchdog = threading.Thread(target=self._deadlines, name="benchmark-deadlines")
                self.watchdog.start()
        except Exception:
            self.close()
            raise

    @property
    def available(self) -> bool:
        return self.enabled and not self.closing and not self.broken

    @property
    def unavailable_reason(self) -> str | None:
        if self.broken:
            return "storage_unavailable"
        if self.closing:
            return "lifecycle_unavailable"
        if self.registry is None:
            return "registry_unconfigured"
        if self.executor is None:
            return "executor_unconfigured"
        return None if self.enabled else "execution_not_approved"

    def _plan(self, request: BenchmarkRequest):
        analysis = self.storage.get(request.analysis_id)
        self.access.select(analysis.repository_path)
        if not self.enabled:
            raise ServiceError("capability_unavailable")
        try:
            return self.registry.resolve(request, analysis, self.settings, self.executor)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError("capability_unavailable") from None

    def _authorized_job(self, run_id: str) -> JobResponse:
        job = self.storage.get_job(run_id)
        analysis = self.storage.get(job.plan.analysis_id)
        self.access.select(analysis.repository_path)
        return job

    def submit(self, request: BenchmarkRequest, check=lambda: None) -> JobAccepted:
        request = BenchmarkRequest.model_validate(request)
        # Validate the analysis even when execution is unconfigured: unknown
        # analyses remain 404, while missing execution prerequisites are 503.
        plan = self._plan(request)
        enqueued = []
        with self.condition:
            if not self.available:
                raise ServiceError("capability_unavailable")
            check()

            def enqueue(run_id):
                if len(self.queue) >= self.settings.max_queued_jobs:
                    raise ServiceError("capacity_exceeded")
                self.queue.append(run_id)
                enqueued.append(run_id)

            try:
                job = self.storage.create_job(request, plan, enqueue)
            except Exception as error:
                for run_id in enqueued:
                    self.queue.remove(run_id)
                if isinstance(error, ServiceError) and error.code == "capability_unavailable":
                    self._storage_failure()
                raise
            self.condition.notify_all()  # Workers cannot claim before COMMIT.
            return JobAccepted(run_id=job.run_id, status=job.status, provenance=job.plan.provenance,
                               status_url="/api/runs/" + job.run_id)

    def get(self, run_id: str) -> JobResponse:
        return self._authorized_job(run_id)

    def _request_cancel(self, job: JobResponse, reason: str) -> JobResponse:
        if job.status in TERMINAL_JOB_STATES or job.status == "cancelling":
            return job
        if job.status == "queued":
            status = "cancelled" if reason == "requested" else "error" if reason == "deadline" else "interrupted"
            updated = self.storage.transition_job(job.run_id, ("queued",), status=status, cancellation_reason=reason,
                                                 error_code=None if status == "cancelled" else "deadline_exceeded" if reason == "deadline" else "shutdown")
            if job.run_id in self.queue:
                self.queue.remove(job.run_id)
            return updated
        updated = self.storage.transition_job(job.run_id, ("running",), status="cancelling", cancellation_reason=reason)
        if job.run_id in self.active:
            self.active[job.run_id].set()
        return updated

    def cancel(self, run_id: str) -> JobResponse:
        with self.condition:
            return self._request_cancel(self._authorized_job(run_id), "requested")

    def _recover(self):
        for run_id, state, _deadline in self.storage.nonterminal_jobs():
            job = self.storage.get_job(run_id)
            if state in ("running", "cancelling"):
                self.storage.transition_job(run_id, (state,), status="interrupted", error_code="process_interrupted")
                continue
            try:
                if job.deadline_at <= datetime.now(timezone.utc):
                    self.storage.transition_job(run_id, ("queued",), status="error", error_code="deadline_exceeded")
                    continue
                if not self.enabled or self.executor.idempotent is not True or len(self.queue) >= self.settings.max_queued_jobs:
                    raise ServiceError("capability_unavailable")
                request = BenchmarkRequest(
                    analysis_id=job.plan.analysis_id, node_ids=job.plan.node_ids,
                    baseline_model_id=job.plan.models[0].identifier,
                    candidate_model_ids=[model.identifier for model in job.plan.models[1:]],
                    benchmark_case_set_id=job.plan.case_set.identifier,
                    evaluation_profile_id=job.plan.evaluation_profile.identifier, idempotency_key=job.idempotency_key,
                )
                if self._plan(request) != job.plan:
                    raise ServiceError("source_conflict")
                self.queue.append(run_id)
            except (ServiceError, ValidationError):
                self.storage.transition_job(run_id, ("queued",), status="interrupted", error_code="recovery_unavailable")

    def _storage_failure(self):
        self.broken = True
        for cancellation in self.active.values():
            cancellation.set()
        self.condition.notify_all()
        logging.getLogger("cascaderouter.jobs").error("Job persistence unavailable; lifecycle admission stopped.")

    def _worker(self):
        while True:
            with self.condition:
                while not self.queue and not self.closing and not self.broken:
                    self.condition.wait()
                if self.broken or (self.closing and not self.queue):
                    return
                run_id = self.queue.popleft()
                try:
                    job = self.storage.get_job(run_id)
                    if job.status != "queued":
                        continue
                    if job.deadline_at <= datetime.now(timezone.utc):
                        self._request_cancel(job, "deadline")
                        continue
                    job = self.storage.transition_job(run_id, ("queued",), status="running")
                    cancellation = self.active[run_id] = threading.Event()
                except ServiceError:
                    self._storage_failure()
                    return
            self._execute(job, cancellation)

    def _execute(self, job: JobResponse, cancellation: threading.Event):
        error_code = None
        iterator = None
        try:
            iterator = iter(self.executor.execute(job.plan, cancellation, job.deadline_at))
            for raw in iterator:
                try:
                    measurement = BenchmarkMeasurement.model_validate(raw)
                    if measurement.provenance != job.plan.provenance or measurement.unit_key() not in job.plan.unit_keys():
                        raise ValueError()
                except (ValidationError, TypeError, ValueError):
                    error_code = "invalid_result"
                    break
                with self.condition:
                    try:
                        self.storage.transition_job(job.run_id, ("running", "cancelling"), measurement=measurement)
                    except ServiceError as error:
                        if error.code in ("capacity_exceeded", "source_conflict"):
                            error_code = "invalid_result"
                        else:
                            error_code = "storage_unavailable"
                        break
        except Exception:
            error_code = "executor_failed"
        finally:
            try:
                if iterator is not None and hasattr(iterator, "close"):
                    iterator.close()
            except Exception:
                error_code = "executor_failed"
        # Terminal persistence happens only after iterator execution AND cleanup.
        with self.condition:
            try:
                self._finish(job.run_id, error_code)
            except ServiceError:
                try:
                    self.storage.transition_job(job.run_id, ("running", "cancelling"), status="error", error_code="storage_unavailable")
                except ServiceError:
                    pass  # Keep the last durable state for fail-closed recovery.
                self._storage_failure()
            finally:
                self.active.pop(job.run_id, None)

    def _finish(self, run_id: str, error_code: str | None):
        job = self.storage.get_job(run_id)
        if self.broken and error_code is None:
            error_code = "storage_unavailable"
        if job.status == "running" and datetime.now(timezone.utc) >= job.deadline_at:
            job = self._request_cancel(job, "deadline")
        if error_code:
            self.storage.transition_job(run_id, ("running", "cancelling"), status="error", error_code=error_code)
        elif job.status == "cancelling":
            if job.cancellation_reason == "requested":
                self.storage.transition_job(run_id, ("cancelling",), status="cancelled")
            else:
                shutdown = job.cancellation_reason == "shutdown"
                self.storage.transition_job(run_id, ("cancelling",), status="interrupted" if shutdown else "error",
                                            error_code="shutdown" if shutdown else "deadline_exceeded")
        elif job.progress.completed_units != job.progress.total_units:
            self.storage.transition_job(run_id, ("running",), status="error", error_code="invalid_result")
        else:
            statuses = {item.evaluation_status for item in job.measurements}
            quality = "failed" if "failed" in statuses else "passed" if statuses == {"passed"} else "inconclusive"
            self.storage.transition_job(run_id, ("running",), status="complete",
                                        result=BenchmarkSummary(provenance=job.plan.provenance, evaluation_status=quality))

    def _deadlines(self):
        while not self.stopping.wait(0.05):
            with self.condition:
                if self.broken:
                    return
                try:
                    now = datetime.now(timezone.utc)
                    now_text = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
                    for run_id, status, deadline in self.storage.nonterminal_jobs():
                        # Stored times are canonical UTC. Read large result
                        # payloads only for jobs whose deadline has elapsed.
                        if status in ("queued", "running") and deadline <= now_text:
                            job = self.storage.get_job(run_id)
                            self._request_cancel(job, "deadline")
                except ServiceError:
                    self._storage_failure()
                    return

    def close(self):
        with self.condition:
            if self.closing:
                return
            self.closing = True
            self.stopping.set()
            try:
                for run_id in tuple(self.queue):
                    self._request_cancel(self.storage.get_job(run_id), "shutdown")
                for run_id in tuple(self.active):
                    self._request_cancel(self.storage.get_job(run_id), "shutdown")
            except ServiceError:
                self._storage_failure()
            self.condition.notify_all()
        for worker in self.workers:
            if worker.ident is not None:
                worker.join()  # Honest wait for non-cooperative execution.
        if self.watchdog is not None:
            self.watchdog.join()
        self.lease.__exit__(None, None, None)
