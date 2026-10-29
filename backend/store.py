"""In-memory stores shared by the API handlers (single-process demo server)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from backend.compiler.ast_scanner import RepoScan
from backend.schemas import ScanResult

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
