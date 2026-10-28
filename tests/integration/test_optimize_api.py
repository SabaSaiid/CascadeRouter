"""Reference-only API behavior; test fixtures can never authorize production routes."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.config import BackendConfig
from backend.main import create_app
from backend.schemas import OptimizationRequest, OptimizationResponse


def request_for(sample):
    return OptimizationRequest(analysis_id=sample.job.plan.analysis_id, run_id=sample.job.run_id,
                               case_set=sample.job.plan.case_set, evaluation_profile=sample.job.plan.evaluation_profile).model_dump(mode="json")


def settings_for(env, **changes):
    return BackendConfig(**{**env.settings.model_dump(), "permitted_repository_roots": env.settings.permitted_repository_roots,
                            "storage_directory": env.directory, "optimization_quality_threshold": Decimal("0.92"), **changes})


def test_test_job_returns_explicit_unavailable_even_with_test_injection(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    original = env.storage.get_job(sample.job.run_id).model_dump_json()
    before = set(env.repository.iterdir())
    with TestClient(create_app(settings_for(env), benchmark_registry=sample.registry, benchmark_executor=sample.executor,
                               allow_test_benchmarks=True), base_url="http://localhost") as client:
        responses = [client.post("/api/optimize", json=request_for(sample)) for _ in range(2)]
        assert all(item.status_code == 200 for item in responses)
        assert responses[0].content == responses[1].content
        result = OptimizationResponse.model_validate_json(responses[0].content)
        assert result.result.status == "unavailable" and result.result.diagnostics == ("test_evidence",)
        assert result.result.provenance == "test" and not result.result.decisions_complete
        assert result.policy.status == "unavailable" and result.policy.yaml_content is None
        assert result.result.decisions[0].selected_model_id is None
        assert not client.get("/api/health").json()["optimization_available"]
        assert client.get("/api/runs/" + sample.job.run_id).text == original
        schema = client.get("/openapi.json").json()
        assert "/api/optimize" in schema["paths"]
    assert set(env.repository.iterdir()) == before and env.storage.get_job(sample.job.run_id).model_dump_json() == original
    assert "PRIVATE_" not in responses[0].text


@pytest.mark.parametrize("field,value", [
    ("quality_threshold", 0.92), ("cost_usd", "0.01"), ("quality_score", 1),
    ("recordings_path", "PRIVATE_FILE"), ("provenance", "recorded"), ("selected_model_id", "other"),
    ("run_id", "../../PRIVATE"), ("analysis_id", True),
])
def test_caller_cannot_submit_metrics_approval_paths_or_model_choices(optimization_environment, field, value):
    env = optimization_environment
    sample = env.build_optimization()
    with TestClient(create_app(settings_for(env)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json={**request_for(sample), field: value})
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
        assert "PRIVATE" not in response.text


@pytest.mark.parametrize("field,value", [("analysis_id", "analysis_" + "0" * 32), ("run_id", "run_" + "0" * 32)])
def test_unknown_persisted_ids_return_controlled_not_found(optimization_environment, field, value):
    env = optimization_environment
    sample = env.build_optimization()
    with TestClient(create_app(settings_for(env)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json={**request_for(sample), field: value})
        assert response.status_code == 404 and response.json()["code"] == "not_found"


@pytest.mark.parametrize("field", ["case_set", "evaluation_profile"])
def test_different_versions_cannot_be_combined(optimization_environment, field):
    env = optimization_environment
    sample = env.build_optimization()
    body = request_for(sample)
    body[field]["version"] = "v2"
    with TestClient(create_app(settings_for(env)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json=body)
        assert response.status_code == 409 and response.json()["code"] == "source_conflict"


def test_different_analysis_snapshot_is_rejected(optimization_environment):
    from backend.schemas import ScanResponse
    env = optimization_environment
    sample = env.build_optimization()
    other = ScanResponse.model_validate({**env.analysis.model_dump(), "analysis_id": "analysis_" + "0" * 32})
    env.storage.save(other)
    with TestClient(create_app(settings_for(env)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json={**request_for(sample), "analysis_id": other.analysis_id})
        assert response.status_code == 409 and response.json()["code"] == "source_conflict"


def test_current_root_policy_protects_optimization(optimization_environment, tmp_path):
    env = optimization_environment
    sample = env.build_optimization()
    outside = tmp_path / "different-approved-root"
    outside.mkdir()
    with TestClient(create_app(settings_for(env, permitted_repository_roots=[outside])), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json=request_for(sample))
        assert response.status_code == 403 and response.json()["code"] == "repository_forbidden"


def test_unconfigured_api_and_unexpected_failures_are_sanitized(optimization_environment, monkeypatch, caplog):
    from backend.services.optimization import OptimizationService
    env = optimization_environment
    sample = env.build_optimization()
    with TestClient(create_app(), base_url="http://localhost") as client:
        assert client.post("/api/optimize", json=request_for(sample)).status_code == 503
    def fail(*args):
        raise RuntimeError("PRIVATE_OPTIMIZER_EXCEPTION")
    monkeypatch.setattr(OptimizationService, "optimize", fail)
    with TestClient(create_app(settings_for(env)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json=request_for(sample))
        assert response.status_code == 500 and response.json()["code"] == "internal_error"
        assert "PRIVATE_OPTIMIZER_EXCEPTION" not in response.text + caplog.text


@pytest.mark.parametrize("changes", [{"max_benchmark_units": 1}, {"max_job_result_bytes": 1024}])
def test_configured_work_and_response_limits_are_enforced(optimization_environment, changes):
    env = optimization_environment
    sample = env.build_optimization()
    with TestClient(create_app(settings_for(env, **changes)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json=request_for(sample))
        assert response.status_code == 429 and response.json()["code"] == "capacity_exceeded"


def test_endpoint_inherits_body_and_origin_controls(optimization_environment):
    env = optimization_environment
    sample = env.build_optimization()
    with TestClient(create_app(settings_for(env, max_request_body_bytes=128)), base_url="http://localhost") as client:
        response = client.post("/api/optimize", json=request_for(sample))
        assert response.status_code == 413 and response.json()["code"] == "request_too_large"
        response = client.post("/api/optimize", json={}, headers={"Origin": "https://untrusted.invalid"})
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
