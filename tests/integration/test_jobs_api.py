"""In-process lifecycle API; all injected results are explicitly test provenance."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.config import BackendConfig
from backend.main import create_app
from backend.schemas import ErrorResponse, JobAccepted, JobResponse, ScanResponse, TERMINAL_JOB_STATES


def client_for(env, **changes):
    settings = changes.pop("settings", env.settings)
    return TestClient(create_app(settings, benchmark_registry=changes.pop("registry", env.registry),
                                benchmark_executor=changes.pop("executor", env.executor),
                                allow_test_benchmarks=changes.pop("allow_test", True)), base_url="http://localhost")


def error(response, status, code):
    assert response.status_code == status, response.text
    body = ErrorResponse.model_validate_json(response.content)
    assert body.code == code and body.request_id is not None


def wait_for(client, run_id, expected=None):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200
        job = JobResponse.model_validate_json(response.content)
        if (expected is None and job.status in TERMINAL_JOB_STATES) or job.status == expected:
            return job
        time.sleep(0.01)
    pytest.fail("HTTP job did not reach the expected state.")


def test_real_http_acceptance_and_persisted_test_provenance(job_environment):
    env = job_environment
    with client_for(env) as client:
        health = client.get("/api/health").json()
        assert health["benchmark_available"] and health["benchmark_provenance"] == "test"
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        assert response.status_code == 202
        accepted = JobAccepted.model_validate_json(response.content)
        assert accepted.status == "queued" and accepted.provenance == "test"
        assert accepted.status_url == "/api/runs/" + accepted.run_id
        job = wait_for(client, accepted.run_id)
        assert job.status == "complete" and job.result.evaluation_status == "inconclusive"
        assert job.plan.analysis_id == env.analysis.analysis_id and job.plan.provenance == "test"
        assert job.plan.models[0].identifier == env.request.baseline_model_id
        assert all(item.cost_usd.value is None and item.latency_ms.value is None for item in job.measurements)
        assert "PRIVATE_LOCAL_CASE_INPUT" not in job.model_dump_json()
        assert client.post(accepted.status_url + "/cancel").json()["status"] == "complete"
        schema = client.get("/openapi.json").json()
        post = schema["paths"]["/api/benchmark"]["post"]
        assert post["responses"]["202"]["content"]["application/json"]["schema"]["$ref"].endswith("/JobAccepted")
        assert post["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    with client_for(env, executor=None) as client:
        # Finished records remain retrievable when new execution is unavailable.
        assert JobResponse.model_validate_json(client.get(accepted.status_url).content) == job


@pytest.mark.parametrize("missing", ["executor", "registry", "test_opt_in", "all"])
def test_creation_fails_closed_without_approved_execution(job_environment, missing):
    env = job_environment
    changes = {"executor": None} if missing == "executor" else {"registry": None} if missing == "registry" else {"allow_test": False} if missing == "test_opt_in" else {"executor": None, "registry": None}
    with client_for(env, **changes) as client:
        health = client.get("/api/health").json()
        assert not health["benchmark_available"] and health["benchmark_provenance"] is None
        assert health["benchmark_unavailable_reason"] == {
            "executor": "executor_unconfigured", "registry": "registry_unconfigured",
            "test_opt_in": "execution_not_approved", "all": "registry_unconfigured",
        }[missing]
        error(client.post("/api/benchmark", json=env.request.model_dump(mode="json")), 503, "capability_unavailable")
    assert not env.executor.calls


def test_unknown_analysis_and_unknown_runs_are_not_found(job_environment):
    env = job_environment
    with client_for(env) as client:
        request = {**env.request.model_dump(mode="json"), "analysis_id": "analysis_" + "0" * 32}
        error(client.post("/api/benchmark", json=request), 404, "not_found")
        error(client.get("/api/runs/run_" + "0" * 32), 404, "not_found")
        error(client.post("/api/runs/run_" + "0" * 32 + "/cancel"), 404, "not_found")
        error(client.get("/api/runs/PRIVATE_INVALID_ID"), 422, "invalid_request")


@pytest.mark.parametrize("change", [
    {"node_ids": ["bad"]}, {"node_ids": []}, {"analysis_id": 1}, {"candidate_model_ids": "model"},
    {"command": "PRIVATE_EXECUTION"}, {"provider_api_key": "PRIVATE_CREDENTIAL"},
])
def test_invalid_requests_are_controlled(job_environment, change):
    with client_for(job_environment) as client:
        response = client.post("/api/benchmark", json={**job_environment.request.model_dump(mode="json"), **change})
        error(response, 422, "invalid_request")
        assert "PRIVATE_" not in response.text


@pytest.mark.parametrize("field", ["benchmark_case_set_id", "evaluation_profile_id", "baseline_model_id", "node_ids"])
def test_unknown_registry_and_analysis_selections_are_rejected(job_environment, field):
    value = ["llm_" + "0" * 24] if field == "node_ids" else "unknown"
    with client_for(job_environment) as client:
        error(client.post("/api/benchmark", json={**job_environment.request.model_dump(mode="json"), field: value}),
              422, "invalid_request")


def test_partial_analysis_is_inconclusive_and_not_accepted(job_environment):
    env = job_environment
    partial = ScanResponse.model_validate({**env.analysis.model_dump(), "analysis_id": "analysis_" + "b" * 32,
                                           "graph_complete": False, "complete": False})
    env.storage.save(partial)
    with client_for(env) as client:
        error(client.post("/api/benchmark", json={**env.request.model_dump(mode="json"), "analysis_id": partial.analysis_id}),
              409, "source_conflict")
    assert not env.executor.calls


def test_running_and_queued_http_cancellation_are_truthful(job_environment):
    env = job_environment
    env.executor.release.clear()
    env.executor.cooperative = False
    with client_for(env) as client:
        try:
            first = client.post("/api/benchmark", json=env.request.model_dump(mode="json")).json()["run_id"]
            assert env.executor.started.wait(5)
            second = client.post("/api/benchmark", json=env.request.model_dump(mode="json")).json()["run_id"]
            third = client.post("/api/benchmark", json=env.request.model_dump(mode="json")).json()["run_id"]
            error(client.post("/api/benchmark", json=env.request.model_dump(mode="json")), 429, "capacity_exceeded")
            assert client.post("/api/runs/" + second + "/cancel").json()["status"] == "cancelled"
            assert client.post("/api/runs/" + second + "/cancel").json()["status"] == "cancelled"
            assert client.post("/api/runs/" + first + "/cancel").json()["status"] == "cancelling"
            assert client.get("/api/runs/" + first).json()["status"] == "cancelling"
            assert not env.executor.finished.is_set()
        finally:
            env.executor.release.set()
        assert wait_for(client, first).status == "cancelled"
        assert wait_for(client, third).status == "complete"


def test_idempotency_conflict_and_sanitized_executor_error(job_environment):
    env = job_environment
    env.executor.failure = True
    body = {**env.request.model_dump(mode="json"), "idempotency_key": "http-retry"}
    with client_for(env) as client:
        first = client.post("/api/benchmark", json=body)
        assert first.status_code == 202
        run_id = first.json()["run_id"]
        job = wait_for(client, run_id)
        assert job.status == "error" and job.error.code == "executor_failed"
        assert "PRIVATE_EXECUTOR_EXCEPTION" not in job.model_dump_json()
        assert client.post("/api/benchmark", json=body).json()["run_id"] == run_id
        error(client.post("/api/benchmark", json={**body, "node_ids": [env.analysis.nodes[1].node_id]}), 409, "source_conflict")


def test_job_routes_inherit_declared_and_streamed_body_limits(job_environment):
    env = job_environment
    settings = BackendConfig(permitted_repository_roots=env.settings.permitted_repository_roots, storage_directory=env.directory,
                             max_request_body_bytes=64)
    with client_for(env, settings=settings) as client:
        error(client.post("/api/benchmark", content=b"{}", headers={"content-length": "65"}), 413, "request_too_large")
        error(client.post("/api/benchmark", content=iter([b"x" * 32, b"x" * 33])), 413, "request_too_large")
    assert not env.executor.calls


def test_current_root_policy_protects_job_creation_and_reading(job_environment, tmp_path):
    env = job_environment
    with client_for(env) as client:
        run_id = client.post("/api/benchmark", json=env.request.model_dump(mode="json")).json()["run_id"]
        wait_for(client, run_id)
    other = tmp_path / "different-policy"
    other.mkdir()
    settings = BackendConfig(permitted_repository_roots=[other], storage_directory=env.directory)
    with client_for(env, settings=settings) as client:
        error(client.post("/api/benchmark", json=env.request.model_dump(mode="json")), 403, "repository_forbidden")
        error(client.get("/api/runs/" + run_id), 403, "repository_forbidden")
        error(client.post("/api/runs/" + run_id + "/cancel"), 403, "repository_forbidden")


def test_registry_executor_validation_exception_is_safe_and_creates_no_job(job_environment, monkeypatch, caplog):
    env = job_environment

    def failed_plan(plan):
        raise RuntimeError("PRIVATE_PLAN_EXCEPTION")

    monkeypatch.setattr(env.executor, "validate_plan", failed_plan)
    with client_for(env) as client:
        response = client.post("/api/benchmark", json=env.request.model_dump(mode="json"))
        error(response, 503, "capability_unavailable")
        assert "PRIVATE_PLAN_EXCEPTION" not in response.text + caplog.text
    assert env.storage.nonterminal_jobs() == ()


def test_missing_root_or_storage_policy_cannot_be_bypassed_by_jobs(job_environment):
    with client_for(job_environment, settings=BackendConfig()) as client:
        error(client.post("/api/benchmark", json=job_environment.request.model_dump(mode="json")), 503, "capability_unavailable")
        assert not client.get("/api/health").json()["benchmark_available"]
