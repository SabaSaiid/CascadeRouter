"""Bounded, immutable public snapshots in an explicitly configured SQLite store.

The storage directory is trusted operator-owned state, outside all scan roots.
It must not be writable by an untrusted local principal. This is not an OS sandbox.
"""

from __future__ import annotations

import sqlite3
import hashlib
import os
import stat
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator
from uuid import uuid4

from pydantic import ValidationError

from backend.compiler.ast_scanner import _directory_access, _is_link
from backend.config import BackendConfig
from backend.schemas import (
    API_SCHEMA_VERSION, JOB_TRANSITIONS, TERMINAL_JOB_STATES, BenchmarkMeasurement,
    BenchmarkPlan, BenchmarkRequest, BenchmarkVersionRegistration, JobError, JobProgress, JobResponse, ScanResponse,
    OptimizationRecord, OptimizationResponse, PatchProposal, PatchValidationReport, PrivateSourceManifest, content_digest,
)
from .errors import ServiceError


_DDL_V1 = (
    "CREATE TABLE analyses (analysis_id TEXT PRIMARY KEY NOT NULL, created_at TEXT NOT NULL, "
    "schema_version TEXT NOT NULL, completion_status TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_update BEFORE UPDATE ON analyses BEGIN "
    "SELECT RAISE(ABORT, 'immutable snapshot'); END",
    "CREATE TRIGGER immutable_delete BEFORE DELETE ON analyses BEGIN "
    "SELECT RAISE(ABORT, 'immutable snapshot'); END",
)
_DDL_V2 = _DDL_V1 + (
    "CREATE TABLE jobs (run_id TEXT PRIMARY KEY NOT NULL, analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id), "
    "request_key TEXT UNIQUE, request_payload BLOB NOT NULL, plan_payload BLOB NOT NULL, created_at TEXT NOT NULL, "
    "deadline_at TEXT NOT NULL, total_units INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN "
    "('queued','running','cancelling','cancelled','complete','error','interrupted')), updated_at TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_job_plan BEFORE UPDATE OF run_id, analysis_id, request_key, request_payload, plan_payload, "
    "created_at, deadline_at, total_units ON jobs BEGIN SELECT RAISE(ABORT, 'immutable job plan'); END",
    "CREATE TRIGGER immutable_job_terminal BEFORE UPDATE ON jobs WHEN OLD.status IN "
    "('cancelled','complete','error','interrupted') BEGIN SELECT RAISE(ABORT, 'terminal job'); END",
    "CREATE TRIGGER job_transitions BEFORE UPDATE OF status ON jobs WHEN NEW.status != OLD.status AND NOT ("
    "(OLD.status = 'queued' AND NEW.status IN ('running','cancelled','error','interrupted')) OR "
    "(OLD.status = 'running' AND NEW.status IN ('cancelling','complete','error','interrupted')) OR "
    "(OLD.status = 'cancelling' AND NEW.status IN ('cancelled','error','interrupted'))) "
    "BEGIN SELECT RAISE(ABORT, 'invalid job transition'); END",
    "CREATE TRIGGER immutable_job_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT, 'retained job'); END",
)
_DDL_V3 = _DDL_V2 + (
    "CREATE TABLE benchmark_versions (kind TEXT NOT NULL, identifier TEXT NOT NULL, version TEXT NOT NULL, "
    "digest TEXT NOT NULL, provenance TEXT NOT NULL, PRIMARY KEY (kind, identifier, version, provenance))",
    "CREATE TRIGGER immutable_benchmark_version_update BEFORE UPDATE ON benchmark_versions "
    "BEGIN SELECT RAISE(ABORT, 'immutable benchmark version'); END",
    "CREATE TRIGGER immutable_benchmark_version_delete BEFORE DELETE ON benchmark_versions "
    "BEGIN SELECT RAISE(ABORT, 'retained benchmark version'); END",
)
_DDL_V4 = _DDL_V3 + (
    "CREATE TABLE source_manifests (analysis_id TEXT PRIMARY KEY NOT NULL REFERENCES analyses(analysis_id), digest TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_source_update BEFORE UPDATE ON source_manifests BEGIN SELECT RAISE(ABORT, 'immutable source manifest'); END",
    "CREATE TRIGGER immutable_source_delete BEFORE DELETE ON source_manifests BEGIN SELECT RAISE(ABORT, 'retained source manifest'); END",
    "CREATE TABLE optimizations (optimization_id TEXT PRIMARY KEY NOT NULL, analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id), "
    "run_id TEXT NOT NULL REFERENCES jobs(run_id), digest TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_optimization_update BEFORE UPDATE ON optimizations BEGIN SELECT RAISE(ABORT, 'immutable optimization'); END",
    "CREATE TRIGGER immutable_optimization_delete BEFORE DELETE ON optimizations BEGIN SELECT RAISE(ABORT, 'retained optimization'); END",
    "CREATE TABLE patches (patch_id TEXT PRIMARY KEY NOT NULL, analysis_id TEXT NOT NULL REFERENCES source_manifests(analysis_id), "
    "optimization_id TEXT NOT NULL REFERENCES optimizations(optimization_id), digest TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_patch_update BEFORE UPDATE ON patches BEGIN SELECT RAISE(ABORT, 'immutable patch'); END",
    "CREATE TRIGGER immutable_patch_delete BEFORE DELETE ON patches BEGIN SELECT RAISE(ABORT, 'retained patch'); END",
)
_DDL = _DDL_V4 + (
    "CREATE TABLE patch_validations (validation_id TEXT PRIMARY KEY NOT NULL, patch_id TEXT NOT NULL REFERENCES patches(patch_id), "
    "analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id), proposal_digest TEXT NOT NULL, source_manifest_digest TEXT NOT NULL, "
    "digest TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_validation_update BEFORE UPDATE ON patch_validations BEGIN SELECT RAISE(ABORT, 'immutable validation'); END",
    "CREATE TRIGGER immutable_validation_delete BEFORE DELETE ON patch_validations BEGIN SELECT RAISE(ABORT, 'retained validation'); END",
)


class AnalysisStorage:
    def __init__(self, settings: BackendConfig):
        if settings.storage_directory is None:
            raise ServiceError("capability_unavailable")
        self.directory = settings.storage_directory
        info = self.directory.lstat()
        self.identity = info.st_dev, info.st_ino
        self.path = self.directory / "analyses.sqlite3"
        self.max_records = settings.max_stored_analyses
        self.max_bytes = settings.max_stored_analysis_bytes
        self.max_jobs = settings.max_jobs
        self.max_result_bytes = settings.max_job_result_bytes
        self.job_timeout_seconds = settings.job_timeout_seconds
        self.lock = threading.RLock()
        self.closed = False
        self.database_identity: tuple[int, int] | None = None
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                objects = connection.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
                if version == 0 and not objects:
                    for statement in _DDL:
                        connection.execute(statement)
                    connection.execute("PRAGMA user_version = 5")
                elif version in (1, 2, 3, 4):
                    self._check_schema(connection, version=version)
                    previous = {1: _DDL_V1, 2: _DDL_V2, 3: _DDL_V3, 4: _DDL_V4}[version]
                    for statement in _DDL[len(previous):]:
                        connection.execute(statement)
                    connection.execute("PRAGMA user_version = 5")
                else:
                    self._check_schema(connection)
                connection.commit()
            info = self.path.lstat()
            self.database_identity = info.st_dev, info.st_ino
        except (sqlite3.Error, OSError, ServiceError):
            self.closed = True
            raise ServiceError("capability_unavailable") from None

    def _check_schema(self, connection: sqlite3.Connection, version: int = 5) -> None:
        actual_version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
        expected = {1: _DDL_V1, 2: _DDL_V2, 3: _DDL_V3, 4: _DDL_V4, 5: _DDL}[version]
        if actual_version != version or {row[0] for row in objects} != set(expected) or len(objects) != len(expected):
            raise ServiceError("capability_unavailable")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            if self.closed:
                raise ServiceError("capability_unavailable")
            with _directory_access(self.directory, self.directory, self.identity):
                if self.directory.resolve(strict=True) != self.directory:
                    raise ServiceError("capability_unavailable")
                try:
                    info = self.path.lstat()
                except FileNotFoundError:
                    if self.database_identity is not None:
                        raise ServiceError("capability_unavailable") from None
                else:
                    if _is_link(info) or not stat.S_ISREG(info.st_mode) or (
                        self.database_identity is not None
                        and (info.st_dev, info.st_ino) != self.database_identity
                    ):
                        raise ServiceError("capability_unavailable")
                connection = sqlite3.connect(self.path, timeout=0.5)
                try:
                    connection.execute("PRAGMA trusted_schema = OFF")
                    connection.execute("PRAGMA foreign_keys = ON")
                    yield connection
                finally:
                    connection.close()  # Rolls back any uncommitted transaction.

    def save(self, response: ScanResponse, *, source_manifest: PrivateSourceManifest | None = None) -> bytes:
        response = ScanResponse.model_validate(response)
        payload = response.model_dump_json().encode("utf-8")
        if len(payload) > self.max_bytes:
            raise ServiceError("capacity_exceeded")
        private_payload = None
        if source_manifest is not None:
            source_manifest = PrivateSourceManifest.model_validate(source_manifest)
            if (source_manifest.analysis_id != response.analysis_id or source_manifest.digest is None
                    or source_manifest.analysis_digest != hashlib.sha256(payload).hexdigest()):
                raise ServiceError("source_conflict")
            private_payload = source_manifest.model_dump_json().encode("utf-8")
            if len(private_payload) > 4 * 1024 * 1024:
                raise ServiceError("capacity_exceeded")
        try:
            with self._connection() as connection:
                self._check_schema(connection)
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("SELECT 1 FROM analyses WHERE analysis_id = ?", (response.analysis_id,)).fetchone():
                    raise ServiceError("source_conflict")
                if connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] >= self.max_records:
                    raise ServiceError("capacity_exceeded")
                connection.execute(
                    "INSERT INTO analyses (analysis_id, created_at, schema_version, completion_status, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (response.analysis_id, response.model_dump(mode="json", include={"timestamp"})["timestamp"], API_SCHEMA_VERSION,
                     "complete" if response.complete else "partial", payload),
                )
                if private_payload is not None:
                    connection.execute("INSERT INTO source_manifests (analysis_id, digest, payload) VALUES (?, ?, ?)",
                                       (response.analysis_id, source_manifest.digest, private_payload))
                connection.commit()
        except sqlite3.IntegrityError:
            raise ServiceError("source_conflict") from None
        except (sqlite3.Error, OSError):
            raise ServiceError("capability_unavailable") from None
        return payload

    def get(self, analysis_id: str) -> ScanResponse:
        try:
            with self._connection() as connection:
                self._check_schema(connection)
                row = connection.execute(
                    "SELECT created_at, schema_version, completion_status, length(payload) "
                    "FROM analyses WHERE analysis_id = ?", (analysis_id,),
                ).fetchone()
                if row is None:
                    raise ServiceError("not_found")
                if row[1] != API_SCHEMA_VERSION or type(row[3]) is not int or not 0 < row[3] <= self.max_bytes:
                    raise ServiceError("source_conflict")
                payload = connection.execute("SELECT payload FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()[0]
                response = ScanResponse.model_validate_json(payload)
                if (response.analysis_id != analysis_id or response.model_dump(mode="json", include={"timestamp"})["timestamp"] != row[0]
                        or row[2] != ("complete" if response.complete else "partial")):
                    raise ServiceError("source_conflict")
                return response
        except (ValidationError, TypeError, ValueError):
            raise ServiceError("source_conflict") from None
        except (sqlite3.Error, OSError):
            raise ServiceError("capability_unavailable") from None

    def close(self) -> None:
        with self.lock:
            self.closed = True

    def _job_payload(self, job: JobResponse) -> bytes:
        job = JobResponse.model_validate(job)
        measurements = job.model_dump_json(include={"measurements"}).encode("utf-8")
        payload = job.model_dump_json().encode("utf-8")
        if len(measurements) > self.max_result_bytes or len(payload) > self.max_result_bytes + 65536:
            raise ServiceError("capacity_exceeded")
        return payload

    def _job_row(self, connection: sqlite3.Connection, run_id: str) -> JobResponse:
        row = connection.execute(
            "SELECT status, length(plan_payload), created_at, deadline_at, total_units, request_key, updated_at, length(payload), analysis_id "
            "FROM jobs WHERE run_id = ?", (run_id,),
        ).fetchone()
        if row is None:
            raise ServiceError("not_found")
        if (type(row[7]) is not int or not 0 < row[7] <= self.max_result_bytes + 65536
                or type(row[1]) is not int or not 0 < row[1] <= 65536):
            raise ServiceError("source_conflict")
        plan_payload, payload = connection.execute("SELECT plan_payload, payload FROM jobs WHERE run_id = ?", (run_id,)).fetchone()
        job = JobResponse.model_validate_json(payload)
        times = job.model_dump(mode="json", include={"created_at", "updated_at", "deadline_at"})
        if (job.run_id != run_id or job.status != row[0] or job.plan != BenchmarkPlan.model_validate_json(plan_payload)
                or times["created_at"] != row[2] or times["deadline_at"] != row[3]
                or job.progress.total_units != row[4] or job.idempotency_key != row[5] or times["updated_at"] != row[6]
                or job.plan.analysis_id != row[8]):
            raise ServiceError("source_conflict")
        return job

    @contextmanager
    def _job_connection(self):
        try:
            with self._connection() as connection:
                self._check_schema(connection)
                yield connection
        except (ValidationError, TypeError, ValueError):
            raise ServiceError("source_conflict") from None
        except sqlite3.IntegrityError:
            raise ServiceError("source_conflict") from None
        except (sqlite3.Error, OSError):
            raise ServiceError("capability_unavailable") from None

    def create_job(self, request: BenchmarkRequest, plan: BenchmarkPlan, enqueue: Callable[[str], None]) -> JobResponse:
        request = BenchmarkRequest.model_validate(request)
        plan = BenchmarkPlan.model_validate(plan)
        if (request.analysis_id != plan.analysis_id or request.node_ids != plan.node_ids
                or (request.baseline_model_id, *request.candidate_model_ids) != tuple(model.identifier for model in plan.models)
                or request.benchmark_case_set_id != plan.case_set.identifier
                or request.evaluation_profile_id != plan.evaluation_profile.identifier):
            raise ServiceError("source_conflict")
        now = datetime.now(timezone.utc)
        job = JobResponse(run_id="run_" + uuid4().hex, status="queued", plan=plan, created_at=now, updated_at=now,
                          deadline_at=now + timedelta(seconds=self.job_timeout_seconds), idempotency_key=request.idempotency_key,
                          progress=JobProgress(completed_units=0, total_units=len(plan.unit_keys())), measurements=())
        payload = self._job_payload(job)
        request_payload = request.model_dump_json().encode("utf-8")
        plan_payload = plan.model_dump_json().encode("utf-8")
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if request.idempotency_key is not None:
                existing = connection.execute("SELECT run_id, length(request_payload), length(plan_payload) FROM jobs WHERE request_key = ?",
                                              (request.idempotency_key,)).fetchone()
                if existing is not None:
                    if any(type(size) is not int or not 0 < size <= 65536 for size in existing[1:]):
                        raise ServiceError("source_conflict")
                    retained = connection.execute("SELECT request_payload, plan_payload FROM jobs WHERE run_id = ?", (existing[0],)).fetchone()
                    if retained[0] != request_payload or BenchmarkPlan.model_validate_json(retained[1]) != plan:
                        raise ServiceError("source_conflict")
                    return self._job_row(connection, existing[0])
            if connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= self.max_jobs:
                raise ServiceError("capacity_exceeded")
            times = job.model_dump(mode="json", include={"created_at", "updated_at", "deadline_at"})
            connection.execute("INSERT INTO jobs (run_id, analysis_id, request_key, request_payload, plan_payload, "
                               "created_at, deadline_at, total_units, status, updated_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (job.run_id, plan.analysis_id, request.idempotency_key, request_payload, plan_payload,
                                times["created_at"], times["deadline_at"], job.progress.total_units, "queued", times["updated_at"], payload))
            enqueue(job.run_id)  # Caller holds its queue lock through COMMIT.
            connection.commit()
        return job

    def get_job(self, run_id: str) -> JobResponse:
        with self._job_connection() as connection:
            return self._job_row(connection, run_id)

    def get_source_manifest(self, analysis_id):
        with self._job_connection() as connection:
            row = connection.execute("SELECT digest, length(payload) FROM source_manifests WHERE analysis_id = ?", (analysis_id,)).fetchone()
            if row is None:
                raise ServiceError("source_evidence_unavailable")  # Never backfill a historical scan.
            if type(row[1]) is not int or not 0 < row[1] <= 4 * 1024 * 1024:
                raise ServiceError("source_conflict")
            payload = connection.execute("SELECT payload FROM source_manifests WHERE analysis_id = ?", (analysis_id,)).fetchone()[0]
            manifest = PrivateSourceManifest.model_validate_json(payload)
            if manifest.digest != row[0] or manifest.analysis_id != analysis_id:
                raise ServiceError("source_conflict")
            return manifest

    def save_optimization(self, response):
        response = OptimizationResponse.model_validate(response)
        digest = content_digest(response, exclude={"optimization_id"})
        identifier = "opt_" + digest
        if response.optimization_id not in (None, identifier):
            raise ServiceError("source_conflict")
        response = OptimizationResponse.model_validate({**response.model_dump(), "optimization_id": identifier})
        record = OptimizationRecord(optimization_id=identifier, digest=digest, response=response)
        payload = record.model_dump_json().encode("utf-8")
        if len(payload) > self.max_result_bytes + 65536 or len(response.model_dump_json().encode("utf-8")) > self.max_result_bytes:
            raise ServiceError("capacity_exceeded")
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = self._job_row(connection, response.result.run_id)
            if content_digest(job) != response.result.benchmark_digest or job.plan != response.result.plan:
                raise ServiceError("source_conflict")
            existing = connection.execute("SELECT length(payload) FROM optimizations WHERE optimization_id = ?", (identifier,)).fetchone()
            if existing is not None:
                if type(existing[0]) is not int or not 0 < existing[0] <= self.max_result_bytes + 65536:
                    raise ServiceError("source_conflict")
                retained = connection.execute("SELECT payload FROM optimizations WHERE optimization_id = ?", (identifier,)).fetchone()[0]
                if retained != payload:
                    raise ServiceError("source_conflict")
                return response
            if connection.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0] >= self.max_jobs:
                raise ServiceError("capacity_exceeded")
            connection.execute("INSERT INTO optimizations (optimization_id, analysis_id, run_id, digest, payload) VALUES (?, ?, ?, ?, ?)",
                               (identifier, job.plan.analysis_id, job.run_id, digest, payload))
            connection.commit()
        return response

    def get_optimization(self, identifier):
        with self._job_connection() as connection:
            row = connection.execute("SELECT analysis_id, run_id, digest, length(payload) FROM optimizations WHERE optimization_id = ?", (identifier,)).fetchone()
            if row is None:
                raise ServiceError("not_found")
            if type(row[3]) is not int or not 0 < row[3] <= self.max_result_bytes + 65536:
                raise ServiceError("source_conflict")
            payload = connection.execute("SELECT payload FROM optimizations WHERE optimization_id = ?", (identifier,)).fetchone()[0]
            record = OptimizationRecord.model_validate_json(payload)
            if (record.optimization_id != identifier or record.digest != row[2]
                    or record.response.result.plan.analysis_id != row[0] or record.response.result.run_id != row[1]):
                raise ServiceError("source_conflict")
            return record

    def save_patch(self, proposal):
        proposal = PatchProposal.model_validate(proposal)
        manifest = proposal.manifest
        source = self.get_source_manifest(manifest.analysis_id)
        optimization = self.get_optimization(manifest.optimization_id)
        response = optimization.response
        if (manifest.source_manifest_digest != source.digest or manifest.optimization_digest != optimization.digest
                or manifest.analysis_id != response.result.plan.analysis_id or manifest.provenance != response.result.provenance
                or manifest.policy_digest != response.policy.digest
                or not set(manifest.requested_node_ids) <= set(response.result.plan.node_ids)):
            raise ServiceError("source_conflict")
        analysis = self.get(manifest.analysis_id)
        nodes = {item.node_id: item for item in analysis.nodes}
        versions = {item.file_path: item for item in source.files}
        decisions = {item.node_id: item for item in response.result.decisions}
        for file in manifest.files:
            version = versions.get(file.file_path)
            if version is None or file.original_digest != version.sha256:
                raise ServiceError("source_conflict")
            for edit in file.edits:
                node, decision = nodes.get(edit.node_id), decisions.get(edit.node_id)
                if (node is None or decision is None or node.file_path != file.file_path or node.model_resolution != "literal"
                        or decision.status != "recommended" or node.current_model != edit.old_model_id
                        or edit.old_model_id != decision.baseline_model_id or edit.proposed_model_id != decision.selected_model_id
                        or edit.end_byte > version.size):
                    raise ServiceError("source_conflict")
        payload = proposal.model_dump_json().encode("utf-8")
        if len(payload) > self.max_result_bytes:
            raise ServiceError("capacity_exceeded")
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM patches").fetchone()[0] >= self.max_jobs:
                raise ServiceError("capacity_exceeded")
            connection.execute("INSERT INTO patches (patch_id, analysis_id, optimization_id, digest, payload) VALUES (?, ?, ?, ?, ?)",
                               (manifest.patch_id, manifest.analysis_id, manifest.optimization_id, proposal.digest, payload))
            connection.commit()

    def get_patch(self, identifier):
        with self._job_connection() as connection:
            row = connection.execute("SELECT analysis_id, optimization_id, digest, length(payload) FROM patches WHERE patch_id = ?", (identifier,)).fetchone()
            if row is None:
                raise ServiceError("not_found")
            if type(row[3]) is not int or not 0 < row[3] <= self.max_result_bytes:
                raise ServiceError("source_conflict")
            payload = connection.execute("SELECT payload FROM patches WHERE patch_id = ?", (identifier,)).fetchone()[0]
            proposal = PatchProposal.model_validate_json(payload)
            if (proposal.manifest.patch_id != identifier or proposal.manifest.analysis_id != row[0]
                    or proposal.manifest.optimization_id != row[1] or proposal.digest != row[2]):
                raise ServiceError("source_conflict")
            return proposal

    def _validation_binding(self, report):
        result = report.result
        proposal = self.get_patch(result.patch_id)
        header = proposal.manifest
        if (result.proposal_digest != proposal.digest or result.analysis_id != header.analysis_id
                or result.source_manifest_digest != header.source_manifest_digest or result.provenance != header.provenance
                or result.omitted_nodes != len(header.omissions)):
            raise ServiceError("source_conflict")
        files = {file.file_path: file for file in header.files}
        for file in result.files:
            original = files.get(file.file_path)
            if original is None or file.original_digest != original.original_digest:
                raise ServiceError("source_conflict")
            if file.candidate_digest is not None and ((file.candidate_digest == original.proposed_digest) != (file.reason != "candidate_digest_mismatch")):
                raise ServiceError("source_conflict")
        if result.status in ("validated", "partial") and (
                {file.file_path for file in result.files} != files.keys()
                or result.complete != header.complete_for_requested_nodes):
            raise ServiceError("source_conflict")
        if result.reason == "no_editable_files" and header.files:
            raise ServiceError("source_conflict")

    def save_validation(self, report):
        report = PatchValidationReport.model_validate(report)
        payload = report.model_dump_json().encode("utf-8")
        if len(payload) > self.max_result_bytes:
            raise ServiceError("capacity_exceeded")
        self._validation_binding(report)
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT length(payload) FROM patch_validations WHERE validation_id = ?", (report.validation_id,)).fetchone()
            if existing is not None:
                if type(existing[0]) is not int or not 0 < existing[0] <= self.max_result_bytes:
                    raise ServiceError("source_conflict")
                retained = self.get_validation(report.validation_id)
                if retained != report:
                    raise ServiceError("source_conflict")
                return retained
            if connection.execute("SELECT COUNT(*) FROM patch_validations").fetchone()[0] >= self.max_jobs:
                raise ServiceError("capacity_exceeded")
            result = report.result
            connection.execute("INSERT INTO patch_validations (validation_id, patch_id, analysis_id, proposal_digest, source_manifest_digest, digest, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (report.validation_id, result.patch_id, result.analysis_id, result.proposal_digest, result.source_manifest_digest, report.digest, payload))
            connection.commit()
        return report

    def get_validation(self, identifier):
        with self._job_connection() as connection:
            row = connection.execute("SELECT patch_id, analysis_id, proposal_digest, source_manifest_digest, digest, length(payload) FROM patch_validations WHERE validation_id = ?", (identifier,)).fetchone()
            if row is None:
                raise ServiceError("not_found")
            if type(row[5]) is not int or not 0 < row[5] <= self.max_result_bytes:
                raise ServiceError("source_conflict")
            payload = connection.execute("SELECT payload FROM patch_validations WHERE validation_id = ?", (identifier,)).fetchone()[0]
            report = PatchValidationReport.model_validate_json(payload)
            result = report.result
            if (report.validation_id != identifier or (result.patch_id, result.analysis_id, result.proposal_digest,
                    result.source_manifest_digest, report.digest) != row[:5]):
                raise ServiceError("source_conflict")
            self._validation_binding(report)
            return report

    def transition_job(self, run_id: str, expected: tuple[str, ...], *, status: str | None = None,
                       measurement: BenchmarkMeasurement | None = None, cancellation_reason: str | None = None,
                       error_code: str | None = None, result=None) -> JobResponse:
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = self._job_row(connection, run_id)
            if old.status not in expected or old.status in TERMINAL_JOB_STATES:
                raise ServiceError("source_conflict")
            new_status = old.status if status is None else status
            if status is not None and status not in JOB_TRANSITIONS[old.status]:
                raise ServiceError("source_conflict")
            if measurement is not None and old.status not in ("running", "cancelling"):
                raise ServiceError("source_conflict")
            data = old.model_dump()
            now = datetime.now(timezone.utc)
            data.update(status=new_status, updated_at=now, result=result)
            if measurement is not None:
                data["measurements"] = (*old.measurements, measurement)
                data["progress"] = JobProgress(completed_units=len(old.measurements) + 1, total_units=old.progress.total_units)
            if cancellation_reason is not None:
                data["cancellation_reason"] = cancellation_reason
            if error_code is not None:
                data["error"] = JobError(code=error_code)
            if new_status in TERMINAL_JOB_STATES:
                data["finished_at"] = now
            updated = JobResponse.model_validate(data)
            payload = self._job_payload(updated)
            connection.execute("UPDATE jobs SET status = ?, updated_at = ?, payload = ? WHERE run_id = ? AND status = ?",
                               (updated.status, updated.model_dump(mode="json", include={"updated_at"})["updated_at"],
                                payload, run_id, old.status))
            connection.commit()
            return updated

    def nonterminal_jobs(self) -> tuple[tuple[str, str, str], ...]:
        with self._job_connection() as connection:
            rows = connection.execute("SELECT run_id, status, deadline_at FROM jobs WHERE status IN ('queued','running','cancelling') "
                                      "ORDER BY created_at, run_id LIMIT 2049").fetchall()
            if len(rows) > 2048:
                raise ServiceError("capacity_exceeded")
            return tuple(rows)

    def register_benchmark_versions(self, records):
        if type(records) not in (tuple, list) or len(records) > 2048:
            raise ServiceError("capacity_exceeded")
        try:
            entries = tuple(BenchmarkVersionRegistration(kind=row[0], identifier=row[1], version=row[2],
                                                         digest=row[3], provenance=row[4]) for row in records)
        except (ValidationError, IndexError, TypeError):
            raise ServiceError("source_conflict") from None
        keys = [(item.kind, item.identifier, item.version, item.provenance) for item in entries]
        if len(keys) != len(set(keys)):
            raise ServiceError("source_conflict")
        with self._job_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT COUNT(*) FROM benchmark_versions").fetchone()[0]
            for item, key in zip(entries, keys):
                row = connection.execute("SELECT digest FROM benchmark_versions WHERE kind = ? AND identifier = ? AND version = ? AND provenance = ?", key).fetchone()
                if row is not None:
                    if row[0] != item.digest:
                        raise ServiceError("source_conflict")
                    continue
                if count >= 16384:
                    raise ServiceError("capacity_exceeded")
                connection.execute("INSERT INTO benchmark_versions (kind, identifier, version, provenance, digest) VALUES (?, ?, ?, ?, ?)", (*key, item.digest))
                count += 1
            connection.commit()

    def verify_benchmark_versions(self, records):
        """Read-only check of already registered identities; never auto-register evidence."""
        if type(records) not in (tuple, list) or len(records) > 2048:
            raise ServiceError("capacity_exceeded")
        try:
            entries = tuple(BenchmarkVersionRegistration(kind=row[0], identifier=row[1], version=row[2],
                                                         digest=row[3], provenance=row[4]) for row in records)
        except (ValidationError, IndexError, TypeError):
            raise ServiceError("source_conflict") from None
        with self._job_connection() as connection:
            for item in entries:
                row = connection.execute(
                    "SELECT digest FROM benchmark_versions WHERE kind = ? AND identifier = ? AND version = ? AND provenance = ?",
                    (item.kind, item.identifier, item.version, item.provenance),
                ).fetchone()
                if row is None or row[0] != item.digest:
                    raise ServiceError("source_conflict")

    @contextmanager
    def job_lease(self):
        """One lifecycle owner per database, including across local processes."""
        descriptor = None
        locked = False
        with _directory_access(self.directory, self.directory, self.identity):
            try:
                path = self.directory / "jobs.lock"
                try:
                    before = path.lstat()
                except FileNotFoundError:
                    before = None
                if before is not None and (_is_link(before) or not stat.S_ISREG(before.st_mode)):
                    raise ServiceError("capability_unavailable")
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0), 0o600)
                opened, after = os.fstat(descriptor), path.lstat()
                if (not stat.S_ISREG(opened.st_mode) or _is_link(after) or opened.st_size > 1
                        or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
                        or (before is not None and (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino))):
                    raise ServiceError("capability_unavailable")
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                yield
            except OSError:
                raise ServiceError("capability_unavailable") from None
            finally:
                if descriptor is not None:
                    if locked:
                        if os.name == "nt":
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)
