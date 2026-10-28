"""Explicit local case registry and recorded replay; no inference or networking.

Case text stays in trusted registry memory. Plans persist identifiers and digests,
never case prompts or expected outputs. Only approved local JSON assets are read.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Protocol

from pydantic import ValidationError

from backend.compiler.ast_scanner import _is_link
from backend.config import BackendConfig
from backend.schemas import (
    BenchmarkMeasurement, BenchmarkPlan, BenchmarkRegistryDocument, BenchmarkRequest,
    RecordingDocument, ScanResponse, VersionedReference,
)
from .errors import ServiceError


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def configuration_digest(settings: BackendConfig) -> str:
    return digest(json.dumps({
        "policy": "zero-cost.jobs.v1", "job_timeout_seconds": settings.job_timeout_seconds,
        "max_benchmark_units": settings.max_benchmark_units, "max_job_result_bytes": settings.max_job_result_bytes,
        "job_workers": settings.job_workers, "max_queued_jobs": settings.max_queued_jobs, "max_jobs": settings.max_jobs,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class BenchmarkExecutor(Protocol):
    """Trusted synchronous iterator; all work ends when iteration/cleanup ends.

    No work may outlive this call in detached threads/processes. Yield only actual
    finished unit records. Cancellation is cooperative, never thread termination.
    Production accepts the built-in replay executor only; custom injection is test-only.
    """

    provenance: str
    identity: str
    idempotent: bool

    def validate_plan(self, plan: BenchmarkPlan) -> None: ...

    def execute(self, plan: BenchmarkPlan, cancellation: threading.Event, deadline: datetime) -> Iterator[BenchmarkMeasurement]: ...


class BenchmarkRegistry:
    def __init__(self, document: BenchmarkRegistryDocument):
        self.document = BenchmarkRegistryDocument.model_validate(document)
        encoded = self.document.model_dump_json().encode("utf-8")
        if len(encoded) > 1024 * 1024:
            raise ServiceError("capacity_exceeded")
        self.identity = digest(encoded)

    def resolve(self, request: BenchmarkRequest, analysis: ScanResponse, settings: BackendConfig,
                executor: BenchmarkExecutor) -> BenchmarkPlan:
        if not analysis.complete or analysis.data_source != "live":
            raise ServiceError("source_conflict")
        if not set(request.node_ids) <= {node.node_id for node in analysis.nodes}:
            raise ServiceError("invalid_request")
        sets = {item.identifier: item for item in self.document.case_sets}
        profiles = {item.identifier: item for item in self.document.evaluation_profiles}
        models = {item.identifier: item for item in self.document.models}
        requested_models = (request.baseline_model_id, *request.candidate_model_ids)
        if (request.benchmark_case_set_id not in sets or request.evaluation_profile_id not in profiles
                or any(model not in models for model in requested_models)):
            raise ServiceError("invalid_request")
        cases, profile = sets[request.benchmark_case_set_id], profiles[request.evaluation_profile_id]
        if len(request.node_ids) * len(requested_models) * len(cases.cases) > settings.max_benchmark_units:
            raise ServiceError("capacity_exceeded")
        plan = BenchmarkPlan(
            analysis_id=analysis.analysis_id, analysis_digest=digest(analysis.model_dump_json().encode("utf-8")),
            node_ids=request.node_ids, models=[models[model] for model in requested_models],
            case_set=VersionedReference(identifier=cases.identifier, version=cases.version),
            case_ids=[case.identifier for case in cases.cases],
            evaluation_profile=VersionedReference(identifier=profile.identifier, version=profile.version),
            registry_digest=self.identity, configuration_digest=configuration_digest(settings),
            execution_digest=executor.identity, provenance=executor.provenance,
        )
        executor.validate_plan(plan)
        return plan


class ReplayExecutor:
    """Copy approved recorded measurements verbatim; never synthesize measurements."""

    idempotent = True

    def __init__(self, document: RecordingDocument):
        self.document = RecordingDocument.model_validate(document)
        encoded = self.document.model_dump_json().encode("utf-8")
        if len(encoded) > 4 * 1024 * 1024:
            raise ServiceError("capacity_exceeded")
        self.identity = digest(encoded)
        self.provenance = self.document.provenance

    def _measurements(self, plan: BenchmarkPlan):
        for record in self.document.recordings:
            if (record.analysis_id == plan.analysis_id and record.analysis_digest == plan.analysis_digest
                    and record.registry_digest == plan.registry_digest and record.case_set == plan.case_set
                    and record.evaluation_profile == plan.evaluation_profile):
                return {item.unit_key(): item for item in record.measurements}
        raise ServiceError("capability_unavailable")

    def validate_plan(self, plan: BenchmarkPlan) -> None:
        if plan.provenance != self.provenance or plan.execution_digest != self.identity:
            raise ServiceError("capability_unavailable")
        records = self._measurements(plan)
        if not set(plan.unit_keys()) <= records.keys():
            raise ServiceError("capability_unavailable")

    def execute(self, plan: BenchmarkPlan, cancellation: threading.Event, deadline: datetime) -> Iterator[BenchmarkMeasurement]:
        self.validate_plan(plan)
        records = self._measurements(plan)
        for key in plan.unit_keys():
            if cancellation.is_set() or datetime.now(timezone.utc) >= deadline:
                return
            yield records[key]


def _read_asset(path: Path, maximum: int):
    try:
        before = path.lstat()
        if _is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ServiceError("capability_unavailable")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ServiceError("capability_unavailable")
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        if len(data) > maximum or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns,
        ):
            raise ServiceError("capability_unavailable")
        return json.loads(data)
    except (OSError, ValueError, RuntimeError):
        raise ServiceError("capability_unavailable") from None


def load_local_assets(settings: BackendConfig) -> tuple[BenchmarkRegistry | None, ReplayExecutor | None]:
    try:
        registry = None if settings.benchmark_registry_path is None else BenchmarkRegistry(
            BenchmarkRegistryDocument.model_validate(_read_asset(settings.benchmark_registry_path, 1024 * 1024)),
        )
        executor = None if settings.benchmark_recordings_path is None else ReplayExecutor(
            RecordingDocument.model_validate(_read_asset(settings.benchmark_recordings_path, 4 * 1024 * 1024)),
        )
        if ((registry is not None and registry.document.origin != "local")
                or (executor is not None and executor.provenance != "recorded")):
            raise ServiceError("capability_unavailable")
        return registry, executor
    except (ValidationError, TypeError, ValueError):
        raise ServiceError("capability_unavailable") from None
