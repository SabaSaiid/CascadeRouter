"""End-to-end pipeline on the bundled sample repo, through the library layer.

The LLM is a test double (no network); everything else is real: AST scan,
DAG, sandboxed prompt capture, evaluation, optimisation, policy, patch and
the sandboxed regression run of the patched repository.
"""

import asyncio
from datetime import datetime, timezone

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.dag_builder import build_dag
from backend.compiler.policy_generator import load_policy_text
from backend.compiler.shadow_runner import BenchmarkRunner, RunExtras
from backend.config import REPO_ROOT, load_settings
from backend.runtime.cascade_router import CascadeRouter
from backend.schemas import BenchmarkRun, ScanResult
from backend.services.optimization import optimize_run
from backend.store import StoredRun, StoredScan
from tests.api.conftest import FakeLLM

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def test_sample_repo_end_to_end():
    settings = load_settings()
    repo = scan_repository(SAMPLE)
    edges = build_dag(repo.trees, repo.calls)
    result = ScanResult(repository_path="tests/fixtures/sample_repo", nodes=[c.to_llm_node() for c in repo.calls],
                        graph_edges=edges, timestamp="t", data_source="live",
                        scanned_files_count=repo.scanned_files_count, detected_framework=repo.detected_framework)
    run = BenchmarkRun(run_id="run_it", status="running", progress_pct=0, nodes=[], data_source="live",
                       created_at=datetime.now(timezone.utc).isoformat())
    extras = RunExtras(repo_root=SAMPLE, node_ids=[c.node_id for c in repo.calls], threshold=0.92)
    llm = FakeLLM()
    asyncio.run(BenchmarkRunner(settings, llm).run(run, extras, repo.calls))
    assert run.status == "complete", run.current_step

    out = optimize_run(StoredRun(run=run, extras=extras, scan=StoredScan(repo=repo, result=result)), 0.92, settings)
    assert out.all_regressions_passed, [d.regression_log for d in out.decisions]
    assert out.total_optimized_cost_usd < out.total_baseline_cost_usd
    by_id = {d.node_id: d for d in out.decisions}
    assert by_id["node_generate_support_resolution"].recommended_model == "nvidia/Nemotron-3.5-Super-VL"

    # The emitted policy drives the runtime exactly as decided.
    router = CascadeRouter.from_dict(load_policy_text(out.combined_policy_yaml))
    for d in out.decisions:
        assert router.rules[d.node_id].primary_model == d.recommended_model
        assert router.rules[d.node_id].fallback_model == d.fallback_model
