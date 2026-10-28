"""Bounded, immutable public snapshots in an explicitly configured SQLite store.

The storage directory is trusted operator-owned state, outside all scan roots.
It must not be writable by an untrusted local principal. This is not an OS sandbox.
"""

from __future__ import annotations

import sqlite3
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
_DDL = _DDL_V2 + (
    "CREATE TABLE benchmark_versions (kind TEXT NOT NULL, identifier TEXT NOT NULL, version TEXT NOT NULL, "
    "digest TEXT NOT NULL, provenance TEXT NOT NULL, PRIMARY KEY (kind, identifier, version, provenance))",
    "CREATE TRIGGER immutable_benchmark_version_update BEFORE UPDATE ON benchmark_versions "
    "BEGIN SELECT RAISE(ABORT, 'immutable benchmark version'); END",
    "CREATE TRIGGER immutable_benchmark_version_delete BEFORE DELETE ON benchmark_versions "
    "BEGIN SELECT RAISE(ABORT, 'retained benchmark version'); END",
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
                    connection.execute("PRAGMA user_version = 3")
                elif version in (1, 2):
                    self._check_schema(connection, version=version)
                    previous = _DDL_V1 if version == 1 else _DDL_V2
                    for statement in _DDL[len(previous):]:
                        connection.execute(statement)
                    connection.execute("PRAGMA user_version = 3")
                else:
                    self._check_schema(connection)
                connection.commit()
            info = self.path.lstat()
            self.database_identity = info.st_dev, info.st_ino
        except (sqlite3.Error, OSError, ServiceError):
            self.closed = True
            raise ServiceError("capability_unavailable") from None

    def _check_schema(self, connection: sqlite3.Connection, version: int = 3) -> None:
        actual_version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
        expected = _DDL_V1 if version == 1 else _DDL_V2 if version == 2 else _DDL
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

    def save(self, response: ScanResponse) -> bytes:
        response = ScanResponse.model_validate(response)
        payload = response.model_dump_json().encode("utf-8")
        if len(payload) > self.max_bytes:
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
