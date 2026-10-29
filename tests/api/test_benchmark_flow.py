import time

import pytest

from backend.config import REPO_ROOT, load_settings

SAMPLE = "tests/fixtures/sample_repo"
S = load_settings()
NANO, LIGHT, SUPER, ULTRA = (m.id for m in S.models)


def _scan(client):
    body = client.post("/api/scan", json={"repository_path": SAMPLE}).json()
    return [n["node_id"] for n in body["nodes"]]


def _wait(client, run_id, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.1)
    raise AssertionError("benchmark did not finish")


def test_full_flow_matches_frontend_contract(client, fake_llm):
    ids = _scan(client)
    r = client.post("/api/benchmark", json={"node_ids": ids})  # exact frontend payload
    assert r.status_code == 202 and set(r.json()) == {"run_id"}
    run = _wait(client, r.json()["run_id"])
    assert run["status"] == "complete" and run["progress_pct"] == 100
    assert run["data_source"] == "live"
    assert len(fake_llm.calls) == 24
    by_id = {n["node_id"]: n for n in run["nodes"]}
    assert by_id["node_classify_customer_intent"]["recommended_model_id"] in (NANO, LIGHT)
    assert by_id["node_generate_support_resolution"]["recommended_model_id"] == SUPER
    cell = by_id["node_generate_support_resolution"]["metrics_by_model"][NANO]
    assert cell["passes_validation"] is False and cell["status"] == "completed"

    o = client.post("/api/optimize", json={"run_id": run["run_id"], "quality_threshold": 0.92})
    assert o.status_code == 200
    body = o.json()
    assert body["all_regressions_passed"] is True, [d["regression_log"] for d in body["decisions"]]
    assert body["total_cost_reduction_pct"] > 50
    assert {d["status"] for d in body["decisions"]} == {"optimized"}
    assert "cascade_router.dispatch(" in body["combined_patch_diff"]
    assert body["combined_policy_yaml"].startswith("version: '1.0'")
    # cached second call returns identical result without re-running the sandbox
    assert client.post("/api/optimize", json={"run_id": run["run_id"], "quality_threshold": 0.92}).json() == body


def test_benchmark_requires_scan(client):
    r = client.post("/api/benchmark", json={"node_ids": ["node_x"]})
    assert r.status_code == 409 and "scan" in r.json()["detail"]


def test_benchmark_rejects_unknown_nodes(client):
    _scan(client)
    r = client.post("/api/benchmark", json={"node_ids": ["node_classify_customer_intent", "node_nope"]})
    assert r.status_code == 409  # no scan contains both


def test_benchmark_with_repository_path(client):
    _scan(client)
    r = client.post("/api/benchmark", json={"node_ids": ["node_nope"], "repository_path": SAMPLE})
    assert r.status_code == 400 and "node_nope" in r.json()["detail"]
    r = client.post("/api/benchmark", json={"node_ids": ["node_x"], "repository_path": "/etc"})
    assert r.status_code == 400


def test_benchmark_validation(client):
    assert client.post("/api/benchmark", json={"node_ids": []}).status_code == 422
    assert client.post("/api/benchmark", json={}).status_code == 422


def test_unknown_run_and_optimize(client):
    assert client.get("/api/runs/run_missing").status_code == 404
    assert client.post("/api/optimize", json={"run_id": "run_missing"}).status_code == 404
    assert client.post("/api/optimize", json={"run_id": "r", "quality_threshold": 2}).status_code == 422


def test_optimize_before_complete_is_409(client, runs, fake_llm):
    import asyncio

    async def slow(model, messages, params):
        await asyncio.sleep(30)

    fake_llm.complete = slow
    ids = _scan(client)
    run_id = client.post("/api/benchmark", json={"node_ids": ids[:1]}).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"
    r = client.post("/api/optimize", json={"run_id": run_id})
    assert r.status_code == 409 and "running" in r.json()["detail"]
    runs.get(run_id).task.cancel()


def test_concurrency_limit(client, fake_llm):
    import asyncio

    async def slow(model, messages, params):
        await asyncio.sleep(30)

    fake_llm.complete = slow
    ids = _scan(client)
    for _ in range(S.max_concurrent_runs):
        assert client.post("/api/benchmark", json={"node_ids": ids[:1]}).status_code == 202
    r = client.post("/api/benchmark", json={"node_ids": ids[:1]})
    assert r.status_code == 429


def test_live_without_key_is_503(store, runs):
    from fastapi.testclient import TestClient

    from backend.api.deps import get_run_store, get_scan_store
    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_scan_store] = lambda: store
    app.dependency_overrides[get_run_store] = lambda: runs
    with TestClient(app, base_url="http://localhost") as c:
        ids = _scan(c)
        r = c.post("/api/benchmark", json={"node_ids": ids})
        assert r.status_code == 503 and "NEBIUS_API_KEY" in r.json()["detail"]


def test_recorded_mode_without_recordings_reports_failures(monkeypatch, store, runs, tmp_path):
    from fastapi.testclient import TestClient

    from backend.api.deps import get_run_store, get_scan_store
    from backend.main import create_app

    monkeypatch.setenv("DATA_SOURCE_MODE", "mock")
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path))
    app = create_app()
    app.dependency_overrides[get_scan_store] = lambda: store
    app.dependency_overrides[get_run_store] = lambda: runs
    with TestClient(app, base_url="http://localhost") as c:
        ids = _scan(c)
        run = _wait(c, c.post("/api/benchmark", json={"node_ids": ids[:1]}).json()["run_id"])
    assert run["data_source"] == "recorded"
    metric = next(iter(run["nodes"][0]["metrics_by_model"].values()))
    assert metric["status"] == "failed" and "no recording" in metric["validation_errors"][0]
    assert run["nodes"][0]["recommended_model_id"] is None


def _live_app(store, runs, fake_llm, cap):
    import dataclasses

    from fastapi.testclient import TestClient

    from backend.api.deps import get_llm_client_factory, get_run_store, get_scan_store
    from backend.main import create_app

    s = dataclasses.replace(load_settings(), daily_spend_cap_usd=cap)
    app = create_app(s)
    app.dependency_overrides[get_scan_store] = lambda: store
    app.dependency_overrides[get_run_store] = lambda: runs
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda settings, tracker: fake_llm)
    return TestClient(app, base_url="http://localhost")


def test_projected_cost_over_budget_is_refused(store, runs, fake_llm):
    from backend.api.deps import _tracker_for_cap

    _tracker_for_cap.cache_clear()
    with _live_app(store, runs, fake_llm, cap=0.01) as c:  # 6 cases x 4 models x 2048 out > $0.01
        ids = _scan(c)
        r = c.post("/api/benchmark", json={"node_ids": ids})
        assert r.status_code == 429 and "Projected worst-case cost" in r.json()["detail"]
        assert fake_llm.calls == []


def test_zero_cap_from_explicit_settings_is_honoured(store, runs, fake_llm):
    from backend.api.deps import _tracker_for_cap

    _tracker_for_cap.cache_clear()
    with _live_app(store, runs, fake_llm, cap=0.0) as c:
        ids = _scan(c)
        r = c.post("/api/benchmark", json={"node_ids": ids})
        assert r.status_code == 429 and r.json()["detail"] == "Daily spend cap reached"


def test_projected_cost_helper(tmp_path):
    from backend.api.routes import projected_output_cost

    s = load_settings()
    per_case = sum(m.output_price_per_m for m in s.models) * 2048 / 1e6
    assert projected_output_cost(REPO_ROOT / SAMPLE, ["node_classify_customer_intent"], s) == pytest.approx(3 * per_case)
    (tmp_path / "cascade_cases.yaml").write_text("bad: yaml: [")
    assert projected_output_cost(tmp_path, ["n"], s) == 0.0
