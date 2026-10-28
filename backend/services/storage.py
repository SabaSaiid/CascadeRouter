"""Bounded, immutable public snapshots in an explicitly configured SQLite store.

The storage directory is trusted operator-owned state, outside all scan roots.
It must not be writable by an untrusted local principal. This is not an OS sandbox.
"""

from __future__ import annotations

import sqlite3
import stat
import threading
from contextlib import contextmanager
from typing import Iterator

from pydantic import ValidationError

from backend.compiler.ast_scanner import _directory_access, _is_link
from backend.config import BackendConfig
from backend.schemas import API_SCHEMA_VERSION, ScanResponse
from .errors import ServiceError


_DDL = (
    "CREATE TABLE analyses (analysis_id TEXT PRIMARY KEY NOT NULL, created_at TEXT NOT NULL, "
    "schema_version TEXT NOT NULL, completion_status TEXT NOT NULL, payload BLOB NOT NULL)",
    "CREATE TRIGGER immutable_update BEFORE UPDATE ON analyses BEGIN "
    "SELECT RAISE(ABORT, 'immutable snapshot'); END",
    "CREATE TRIGGER immutable_delete BEFORE DELETE ON analyses BEGIN "
    "SELECT RAISE(ABORT, 'immutable snapshot'); END",
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
                    connection.execute("PRAGMA user_version = 1")
                else:
                    self._check_schema(connection)
                connection.commit()
            info = self.path.lstat()
            self.database_identity = info.st_dev, info.st_ino
        except (sqlite3.Error, OSError, ServiceError):
            self.closed = True
            raise ServiceError("capability_unavailable") from None

    def _check_schema(self, connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute("SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
        if version != 1 or {row[0] for row in objects} != set(_DDL) or len(objects) != len(_DDL):
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
