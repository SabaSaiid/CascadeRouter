"""The real offline engine processes synthetic test-labelled captures in process."""

import hashlib
import json
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.config import BackendConfig
from backend.main import create_app
from backend.schemas import BenchmarkSummary, JobResponse, LocalBenchmarkCase, TERMINAL_JOB_STATES
from backend.services.benchmark_cases import load_local_assets
from backend.services.storage import AnalysisStorage, _DDL_V2


def wait(client, run_id, terminal=True):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200, response.text
        job = JobResponse.model_validate_json(response.content)
        if not terminal or job.status in TERMINAL_JOB_STATES:
            return job
        time.sleep(0.01)
    pytest.fail("Offline job did not finish.")


def test_approved_test_engine_http_results_are_bounded_private_and_persistent(asset_environment):
    env = asset_environment
    with TestClient(create_app(env.settings, allow_test_benchmarks=True), base_url="http://localhost") as client:
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 202
        job = wait(client, response.json()["run_id"])
        assert job.status == "complete" and job.plan.provenance == "test"
        assert job.result.evaluation_status == "passed" and job.result.metrics.passed == 4
        assert job.result.metrics.processing_complete and job.result.metrics.evaluation_complete
        assert job.result.metrics.latency_ms.mean is None and job.result.metrics.cost_usd.total_usd is None
        assert all(item.evaluation.status == "passed" and item.quality_score is None for item in job.measurements)
        assert "PRIVATE_CAPTURE" not in job.model_dump_json() and "PRIVATE_LOCAL_INPUT" not in job.model_dump_json()
        first = job.model_dump_json()
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        # Production cannot execute these test captures, but retained provenance is honest.
        assert not client.get("/api/health").json()["benchmark_available"]
        assert client.get("/api/runs/" + job.run_id).text == first
    database = (env.directory / "analyses.sqlite3").read_bytes()
    assert b"PRIVATE_CAPTURE" not in database and b"PRIVATE_LOCAL_INPUT" not in database


def test_default_product_never_accepts_test_recordings(asset_environment):
    env = asset_environment
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 503 and response.json()["code"] == "capability_unavailable"


@pytest.mark.parametrize("quality", ["failed", "inconclusive"])
def test_processing_completion_is_separate_from_quality(offline_environment, quality):
    env = offline_environment
    cases = [LocalBenchmarkCase(identifier="case-one", input_text="test", expected_output="expected"),
             LocalBenchmarkCase(identifier="case-two", input_text="test", expected_output=None if quality == "inconclusive" else "expected")]
    outputs = {(model.identifier, case.identifier): "expected" if case.identifier == "case-one" else "different-test-output"
               for model in env.registry.document.models for case in cases}
    registry, _, executor = env.make_offline(cases=cases, outputs=outputs)
    with TestClient(create_app(env.settings, benchmark_registry=registry, benchmark_executor=executor,
                               allow_test_benchmarks=True), base_url="http://localhost") as client:
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 202
        job = wait(client, response.json()["run_id"])
        assert job.status == "complete" and job.result.evaluation_status == quality
        assert job.result.metrics.failed == (2 if quality == "failed" else 0)
        assert job.result.metrics.inconclusive == (2 if quality == "inconclusive" else 0)


def test_revoked_or_missing_asset_cannot_be_accepted_after_startup(asset_environment):
    env = asset_environment
    with TestClient(create_app(env.settings, allow_test_benchmarks=True), base_url="http://localhost") as client:
        original = env.recording_path.read_bytes()
        env.recording_path.write_bytes(original + b" ")
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 409
        env.recording_path.unlink()
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 503 and "PRIVATE" not in response.text
        assert env.storage.nonterminal_jobs() == ()


def test_cancellation_waits_for_current_bounded_unit_and_reports_actual_progress(asset_environment, monkeypatch):
    from backend.services import offline_benchmark
    env = asset_environment
    entered, release = threading.Event(), threading.Event()
    original = offline_benchmark.evaluate
    def blocked(*args):
        entered.set()
        assert release.wait(5), "Offline test unit was not released."
        return original(*args)
    monkeypatch.setattr(offline_benchmark, "evaluate", blocked)
    with TestClient(create_app(env.settings, allow_test_benchmarks=True), base_url="http://localhost") as client:
        try:
            response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
            run_id = response.json()["run_id"]
            assert entered.wait(5)
            assert client.post("/api/runs/" + run_id + "/cancel").json()["status"] == "cancelling"
            assert client.get("/api/runs/" + run_id).json()["status"] == "cancelling"
        finally:
            release.set()
        job = wait(client, run_id)
        assert job.status == "cancelled" and job.progress.completed_units == 1 and job.result is None


def test_safe_queued_offline_recovery_executes_once(asset_environment, monkeypatch):
    from backend.services import offline_benchmark
    env = asset_environment
    registry, executor = load_local_assets(env.settings, allow_test_assets=True)
    plan = registry.resolve(env.request, env.analysis, env.settings, executor)
    queued = env.storage.create_job(env.request, plan, lambda _: None)
    calls = []
    original = offline_benchmark.evaluate
    def evaluated(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(offline_benchmark, "evaluate", evaluated)
    for _ in range(2):
        with TestClient(create_app(env.settings, allow_test_benchmarks=True), base_url="http://localhost") as client:
            assert wait(client, queued.run_id).status == "complete"
    assert len(calls) == len(plan.unit_keys())


def test_metric_failure_is_controlled_and_never_becomes_complete(asset_environment, monkeypatch, caplog):
    from backend.compiler import metrics
    env = asset_environment
    def failed(*args):
        raise RuntimeError("PRIVATE_AGGREGATE_EXCEPTION")
    monkeypatch.setattr(metrics, "aggregate", failed)
    with TestClient(create_app(env.settings, allow_test_benchmarks=True), base_url="http://localhost") as client:
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        job = wait(client, response.json()["run_id"])
        assert job.status == "error" and job.error.code == "invalid_result" and job.result is None
        assert "PRIVATE_AGGREGATE_EXCEPTION" not in job.model_dump_json() + caplog.text


def test_version_two_complete_job_remains_readable_after_additive_contract_migration(offline_environment, tmp_path):
    env = offline_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    env.storage.transition_job(job.run_id, ("queued",), status="running")
    for key in plan.unit_keys():
        env.storage.transition_job(job.run_id, ("running",), measurement=env.measurement(key))
    complete = env.storage.transition_job(job.run_id, ("running",), status="complete",
                                         result=BenchmarkSummary(provenance="test", evaluation_status="inconclusive"))
    data = complete.model_dump(mode="json")
    data["plan"].pop("case_set_digest")
    data["plan"].pop("evaluation_profile_digest")
    data["result"].pop("metrics")
    for item in data["measurements"]:
        for field in ("evaluation", "ttft_ms", "calculated_cost", "recording_id", "evidence_digest", "output_available"):
            item.pop(field)
    legacy_dir = tmp_path / "legacy-state"
    legacy_dir.mkdir()
    with sqlite3.connect(legacy_dir / "analyses.sqlite3") as connection:
        for ddl in _DDL_V2:
            connection.execute(ddl)
        connection.execute("PRAGMA user_version = 2")
        analysis = env.analysis.model_dump(mode="json")
        connection.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
                           (analysis["analysis_id"], analysis["timestamp"], analysis["schema_version"], "complete", env.analysis.model_dump_json().encode()))
        connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (data["run_id"], data["plan"]["analysis_id"], None, env.request.model_dump_json().encode(),
                            json.dumps(data["plan"]).encode(), data["created_at"], data["deadline_at"], data["progress"]["total_units"],
                            data["status"], data["updated_at"], json.dumps(data).encode()))
    storage = AnalysisStorage(BackendConfig(permitted_repository_roots=env.settings.permitted_repository_roots, storage_directory=legacy_dir))
    try:
        retained = storage.get_job(job.run_id)
        assert retained.status == "complete" and retained.result.metrics is None
        assert retained.plan.case_set_digest is None
        assert all(item.ttft_ms is None and item.evaluation is None for item in retained.measurements)
    finally:
        storage.close()
