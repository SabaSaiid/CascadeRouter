"""Bounded off-event-loop work; HTTP cancellation never kills Python threads."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from backend.config import BackendConfig
from . import compiler_adapter
from .errors import ServiceError
from .repository_access import RepositoryAccess
from .storage import AnalysisStorage


_CONFLICT_CODES = frozenset({
    "file_changed", "source_file_changed", "source_changed", "source_unavailable",
    "repository_mismatch", "call_sites_mismatch", "call_objects_mismatch", "invalid_scanner_node",
    "invalid_source_fingerprint", "missing_source_fingerprint", "invalid_source_options", "inconsistent_graph",
})


class ScanService:
    def __init__(self, settings: BackendConfig):
        self.access = RepositoryAccess(settings)
        self.storage = AnalysisStorage(settings)
        self.executor = ThreadPoolExecutor(max_workers=settings.scan_workers, thread_name_prefix="repository-scan")
        self.slots = threading.BoundedSemaphore(settings.scan_workers)
        self.closed = False

    async def _run(self, operation, deadline: float) -> bytes:
        if self.closed:
            raise ServiceError("capability_unavailable")
        if not self.slots.acquire(blocking=False):
            raise ServiceError("capacity_exceeded")
        cancelled = threading.Event()

        def work():
            def check():
                if cancelled.is_set() or time.monotonic() >= deadline:
                    raise ServiceError("capability_unavailable")
            check()
            return operation(check)

        try:
            future = self.executor.submit(work)
        except Exception:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: self.slots.release())
        wrapped = asyncio.wrap_future(future)
        # Retrieve late failures so a timed-out request does not produce a raw
        # unhandled-future traceback. The worker slot stays held until done.
        wrapped.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), max(0, deadline - time.monotonic()))
        except TimeoutError:
            cancelled.set()
            raise ServiceError("capability_unavailable") from None
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def scan(self, requested: str, deadline: float) -> bytes:
        analysis_id = "analysis_" + uuid4().hex
        timestamp = datetime.now(timezone.utc)

        def operation(check):
            with self.access.authorize(requested) as path:
                response = compiler_adapter.analyze_for_api(str(path), analysis_id=analysis_id, timestamp=timestamp)
                if response.repository_path != path.as_posix():
                    raise ServiceError("source_conflict")
                if any(item.code in _CONFLICT_CODES for item in (*response.scan_diagnostics, *response.graph_diagnostics)):
                    raise ServiceError("source_conflict")
            check()
            return self.storage.save(response)

        return await self._run(operation, deadline)

    async def retrieve(self, analysis_id: str, deadline: float) -> bytes:
        def operation(check):
            response = self.storage.get(analysis_id)
            self.access.select(response.repository_path)  # Apply the current policy to retained snapshots.
            check()
            return response.model_dump_json().encode("utf-8")
        return await self._run(operation, deadline)

    def close(self) -> None:
        self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.storage.close()
