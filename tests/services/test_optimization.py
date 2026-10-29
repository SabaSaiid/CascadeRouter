from datetime import datetime, timezone

import pytest

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.dag_builder import build_dag
from backend.compiler.regression_runner import RegressionResult
from backend.compiler.shadow_runner import RunExtras
from backend.config import REPO_ROOT, load_settings
from backend.schemas import BenchmarkMetric, BenchmarkRun, NodeBenchmarkResult, ScanResult
from backend.services.optimization import OptimizeError, optimize_run
from backend.store import StoredRun, StoredScan

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"
S = load_settings()
NANO, LIGHT, SUPER, ULTRA = (m.id for m in S.models)


def metric(spec_id, cost, latency, quality=1.0, passes=True):
    spec = S.model_by_id(spec_id)
    return BenchmarkMetric(model_id=spec.id, model_name=spec.name, tier=spec.tier, input_tokens=100,
                           output_tokens=10, total_latency_ms=latency, estimated_cost_usd=cost,
                           quality_score=quality, passes_validation=passes, is_estimated=False, status="completed")


def stored_run(status="complete", synth_passes=False):
    repo = scan_repository(SAMPLE)
    result = ScanResult(repository_path="tests/fixtures/sample_repo", nodes=[c.to_llm_node() for c in repo.calls],
                        graph_edges=build_dag(repo.trees, repo.calls), timestamp="t", data_source="live",
                        scanned_files_count=repo.scanned_files_count, detected_framework=repo.detected_framework)
    nodes = []
    for c in repo.calls:
        small_ok = synth_passes or "generate" not in c.node_id
        nodes.append(NodeBenchmarkResult(node_id=c.node_id, metrics_by_model={
            NANO: metric(NANO, 0.00003, 140, 1.0 if small_ok else 0.5, small_ok),
            LIGHT: metric(LIGHT, 0.00003, 110, 1.0 if small_ok else 0.5, small_ok),
            SUPER: metric(SUPER, 0.00014, 400),
            ULTRA: metric(ULTRA, 0.00046, 1100),
        }))
    run = BenchmarkRun(run_id="run_x", status=status, progress_pct=100, nodes=nodes, data_source="recorded",
                       created_at=datetime.now(timezone.utc).isoformat())
    extras = RunExtras(repo_root=SAMPLE, node_ids=[c.node_id for c in repo.calls], threshold=0.92)
    return StoredRun(run=run, extras=extras, scan=StoredScan(repo=repo, result=result))


def fake_regression(passed=True):
    calls = []

    def run(root, patches, policy_text, timeout):
        calls.append((root, sorted(patches.files), policy_text))
        return RegressionResult(passed, "6 passed in 0.1s" if passed else "1 failed in 0.1s", "log",
                                {"tests/test_agent.py::test_classify_intent": "PASSED" if passed else "FAILED"})

    return run, calls


def test_optimize_full_result():
    regression, calls = fake_regression()
    out = optimize_run(stored_run(), 0.92, S, regression=regression)
    by_id = {d.node_id: d for d in out.decisions}
    assert by_id["node_classify_customer_intent"].recommended_model == LIGHT
    assert by_id["node_generate_support_resolution"].recommended_model == SUPER
    assert all(d.status == "optimized" for d in out.decisions)
    assert out.total_baseline_cost_usd == pytest.approx(0.00138)
    assert out.total_optimized_cost_usd == pytest.approx(0.0002)
    assert out.total_cost_reduction_pct == pytest.approx(85.51, abs=0.01)
    assert out.all_regressions_passed and out.data_source == "recorded"
    assert len(calls) == 1 and calls[0][1] == ["agent/workflow.py"]
    assert "node_classify_customer_intent:" in out.combined_policy_yaml
    assert out.combined_patch_diff.count("cascade_router.dispatch(") == 3
    d = by_id["node_classify_customer_intent"]
    assert d.patch_diff.count("cascade_router.dispatch(") == 1
    assert d.policy_yaml.startswith("node_id: node_classify_customer_intent\n")
    assert d.regression_log == "tests/test_agent.py::test_classify_intent PASSED"


def test_regression_failure_propagates():
    regression, _ = fake_regression(passed=False)
    out = optimize_run(stored_run(), 0.92, S, regression=regression)
    assert not out.all_regressions_passed
    assert all(not d.regression_passed for d in out.decisions)


def test_retained_nodes_need_no_patch_or_regression():
    run = stored_run()
    for n in run.run.nodes:
        for m in n.metrics_by_model.values():
            if m.model_id != ULTRA:
                m.passes_validation, m.quality_score = False, 0.1
    regression2, calls2 = fake_regression()
    out2 = optimize_run(run, 0.92, S, regression=regression2)
    assert calls2 == [] and out2.combined_patch_diff == ""
    assert all(d.status == "baseline_retained" and d.regression_passed for d in out2.decisions)
    assert all(d.regression_log.startswith("No code change") for d in out2.decisions)
    assert out2.total_cost_reduction_pct == 0 and out2.all_regressions_passed


def test_incomplete_run_rejected():
    with pytest.raises(OptimizeError, match="running"):
        optimize_run(stored_run(status="running"), 0.92, S, regression=fake_regression()[0])


def test_real_sandbox_regression_end_to_end():
    out = optimize_run(stored_run(synth_passes=True), 0.92, S)
    assert out.all_regressions_passed, [d.regression_log for d in out.decisions]
    assert all(d.recommended_model == LIGHT for d in out.decisions)


def test_unpatchable_node_is_reported_not_verified(monkeypatch):
    import backend.services.optimization as opt
    from backend.compiler.patch_generator import PatchSet

    def failing_patches(sources, calls, bom_files=()):
        return PatchSet(errors={c.node_id: "only <client>.chat.completions.create(...) calls can be patched" for c in calls})

    monkeypatch.setattr(opt, "build_patches", failing_patches)
    regression, calls = fake_regression()
    out = optimize_run(stored_run(), 0.92, S, regression=regression)
    assert calls == []
    assert all(not d.regression_passed and d.regression_log.startswith("Patch could not be generated") for d in out.decisions)
    assert not out.all_regressions_passed


def test_nodes_missing_from_scan_are_skipped_and_repo_name_outside_root(tmp_path):
    run = stored_run()
    run.run.nodes[0].node_id = "node_gone"
    run.extras.repo_root = tmp_path / "elsewhere"
    out = optimize_run(run, 0.92, S, regression=fake_regression()[0])
    assert "node_gone" not in {d.node_id for d in out.decisions} and len(out.decisions) == 2
    assert "repository: elsewhere" in out.combined_policy_yaml
