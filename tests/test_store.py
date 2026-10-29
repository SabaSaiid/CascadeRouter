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


# ---------------------------------------------------------------- RunStore

from datetime import datetime, timezone  # noqa: E402

from backend.compiler.shadow_runner import RunExtras  # noqa: E402
from backend.schemas import BenchmarkRun  # noqa: E402
from backend.store import RunStore, StoredRun  # noqa: E402


def _run(run_id: str, status: str = "complete") -> StoredRun:
    run = BenchmarkRun(run_id=run_id, status=status, progress_pct=0, nodes=[], data_source="live",
                       created_at=datetime.now(timezone.utc).isoformat())
    return StoredRun(run=run, extras=RunExtras(repo_root=Path("/r"), node_ids=[], threshold=0.92), scan=_scan("/r"))


def test_run_store_get_and_running_count():
    s = RunStore()
    s.put(_run("a", "running"))
    s.put(_run("b"))
    assert s.get("a").run.status == "running" and s.get("missing") is None
    assert s.running_count() == 1


def test_run_store_evicts_oldest_finished_but_keeps_running():
    s = RunStore(max_items=2)
    s.put(_run("old_running", "running"))
    s.put(_run("done1"))
    s.put(_run("done2"))
    assert s.get("old_running") is not None  # never evicted while running
    assert s.get("done1") is None and s.get("done2") is not None


def test_run_store_optimized_cache_is_per_run():
    a, b = _run("a"), _run("b")
    a.optimized[0.92] = "result"
    assert b.optimized == {}
