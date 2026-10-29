from pathlib import Path

from backend.compiler.ast_scanner import RepoScan
from backend.schemas import ScanResult
from backend.store import ScanStore, StoredScan


def _scan(root: str) -> StoredScan:
    repo = RepoScan(root=Path(root), calls=[], trees={}, sources={}, scanned_files_count=0, detected_framework="x")
    result = ScanResult(repository_path=root, nodes=[], graph_edges=[], timestamp="t",
                        data_source="live", scanned_files_count=0, detected_framework="x")
    return StoredScan(repo=repo, result=result)


def test_latest_and_eviction():
    s = ScanStore(max_items=2)
    assert s.latest() is None
    a, b, c = _scan("/a"), _scan("/b"), _scan("/c")
    s.put(a); s.put(b); s.put(a)  # re-put moves /a to newest
    assert s.latest() is a
    s.put(c)  # evicts /b (oldest)
    assert s.get("/b") is None and s.get("/a") is a and s.latest() is c


def test_find_by_empty_ids_returns_latest():
    s = ScanStore()
    a = _scan("/a")
    s.put(a)
    assert s.find_by_node_ids([]) is a
