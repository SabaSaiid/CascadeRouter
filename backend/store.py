"""In-memory stores shared by the API handlers (single-process demo server)."""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from backend.compiler.ast_scanner import RepoScan
from backend.compiler.shadow_runner import RunExtras
from backend.schemas import BenchmarkRun, ScanResult

MAX_SCANS = 32


@dataclass
class StoredScan:
    repo: RepoScan
    result: ScanResult


class ScanStore:
    """Keeps recent scans keyed by resolved repository path, plus the latest one."""

    def __init__(self, max_items: int = MAX_SCANS) -> None:
        self._items: OrderedDict[str, StoredScan] = OrderedDict()
        self._max = max_items
        self._lock = threading.Lock()

    def put(self, scan: StoredScan) -> None:
        key = str(scan.repo.root)
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = scan
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def get(self, root: str) -> Optional[StoredScan]:
        with self._lock:
            return self._items.get(root)

    def latest(self) -> Optional[StoredScan]:
        with self._lock:
            return next(reversed(self._items.values()), None)

    def find_by_node_ids(self, node_ids: list[str]) -> Optional[StoredScan]:
        """Most recent scan that contains every requested node id."""
        wanted = set(node_ids)
        with self._lock:
            for scan in reversed(self._items.values()):
                if wanted <= {c.node_id for c in scan.repo.calls}:
                    return scan
        return None


MAX_RUNS = 64


@dataclass
class StoredRun:
    run: BenchmarkRun
    extras: RunExtras
    scan: StoredScan
    task: Optional[asyncio.Task[None]] = None


class RunStore:
    """Benchmark runs keyed by run id, oldest evicted first (running ones are kept)."""

    def __init__(self, max_items: int = MAX_RUNS) -> None:
        self._items: OrderedDict[str, StoredRun] = OrderedDict()
        self._max = max_items
        self._lock = threading.Lock()

    def put(self, item: StoredRun) -> None:
        with self._lock:
            self._items[item.run.run_id] = item
            if len(self._items) > self._max:
                for run_id in list(self._items):
                    if len(self._items) <= self._max:
                        break
                    if self._items[run_id].run.status != "running":
                        del self._items[run_id]

    def get(self, run_id: str) -> Optional[StoredRun]:
        with self._lock:
            return self._items.get(run_id)

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for item in self._items.values() if item.run.status == "running")
