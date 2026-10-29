"""Local API boundaries; test-only optimization can never authorize patch creation."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.compiler.policy_generator import generate_policy
from backend.compiler.router_optimizer import optimize
from backend.config import BackendConfig
from backend.main import create_app
from backend.schemas import OptimizationResponse


def body(sample):
    return {"analysis_id": sample.analysis.analysis_id, "optimization_id": sample.record.optimization_id}


def test_new_scan_source_evidence_is_private_and_atomic(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/scan", json={"repository_path": str(env.repository)})
        assert response.status_code == 200
        identifier = response.json()["analysis_id"]
        assert all(name not in response.text for name in ("source_manifest", "fingerprint", "sha256", "inode", "mtime_ns"))
        assert client.get("/api/analyses/" + identifier).content == response.content
        schema = client.get("/openapi.json").json()
        assert "/api/patches" in schema["paths"] and "/api/patches/{patch_id}" in schema["paths"]
        assert client.post("/api/patches/patch_" + "a" * 32 + "/apply", json={}).status_code == 404
    assert env.storage.get_source_manifest(identifier).analysis_id == identifier
    assert (env.repository / "app.py").read_bytes() == sample.raw


def test_test_optimization_is_rejected_even_with_explicit_test_benchmark_injection(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    with TestClient(create_app(env.settings, benchmark_registry=sample.sample.registry, benchmark_executor=sample.sample.executor,
                               allow_test_benchmarks=True), base_url="http://localhost") as client:
        response = client.post("/api/patches", json=body(sample))
        assert response.status_code == 503 and response.json()["code"] == "capability_unavailable"
        assert "local/candidate" not in response.text
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM patches").fetchone()[0] == 0


def test_test_artifact_is_not_exposed_as_production_patch(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.get("/api/patches/" + proposal.manifest.patch_id)
        assert response.status_code == 503 and response.json()["code"] == "capability_unavailable"
        assert "literal-spans" not in response.text and "local/candidate" not in response.text


def test_optimization_api_returns_a_stable_persisted_identity(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    plan = sample.record.response.result.plan
    request = dict(analysis_id=plan.analysis_id, run_id=sample.record.response.result.run_id,
                   case_set=plan.case_set.model_dump(mode="json"), evaluation_profile=plan.evaluation_profile.model_dump(mode="json"))
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        first, second = client.post("/api/optimize", json=request), client.post("/api/optimize", json=request)
        assert first.status_code == second.status_code == 200 and first.content == second.content
        record = env.storage.get_optimization(first.json()["optimization_id"])
        assert record.response.result.provenance == "test" and record.response.result.status == "unavailable"
        assert record.response.model_dump(mode="json") == first.json()


@pytest.mark.parametrize("field,value", [("model_id", "unapproved/model"), ("replacement_model_id", "injected"),
    ("source", "PRIVATE_SOURCE"), ("repository_path", "PRIVATE_PATH"), ("optimization", {"decision": "PRIVATE"}),
    ("command", "PRIVATE_COMMAND"), ("transformation", "execute"), ("node_ids", ["../../PRIVATE"] )])
def test_patch_request_accepts_only_persisted_references(patch_environment, field, value):
    env = patch_environment
    sample = env.build_patch()
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/patches", json={**body(sample), field: value})
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
        assert "PRIVATE" not in response.text


def test_missing_or_unpersisted_artifacts_are_not_found(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        for change in ({"analysis_id": "analysis_" + "0" * 32}, {"optimization_id": "opt_" + "0" * 64}):
            response = client.post("/api/patches", json={**body(sample), **change})
            assert response.status_code == 404 and response.json()["code"] == "not_found"
        response = client.get("/api/patches/patch_" + "0" * 32)
        assert response.status_code == 404 and response.json()["code"] == "not_found"
        assert client.get("/api/patches/../../PRIVATE").status_code == 404


def test_historical_scan_reports_rescan_requirement(patch_environment):
    env = patch_environment
    sample = env.build_optimization()
    result = optimize(sample.snapshot)
    response = env.storage.save_optimization(OptimizationResponse(result=result, policy=generate_policy(result)))
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        reply = client.post("/api/patches", json={"analysis_id": env.analysis.analysis_id, "optimization_id": response.optimization_id})
        assert reply.status_code == 409 and reply.json()["code"] == "source_evidence_unavailable"


def test_current_root_policy_protects_patch_artifacts(patch_environment, tmp_path):
    env = patch_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    other = tmp_path / "other-approved-root"
    other.mkdir()
    settings = BackendConfig(**{**env.settings.model_dump(), "storage_directory": env.directory, "permitted_repository_roots": [other]})
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        for reply in (client.post("/api/patches", json=body(sample)), client.get("/api/patches/" + proposal.manifest.patch_id)):
            assert reply.status_code == 403 and reply.json()["code"] == "repository_forbidden"
            assert "local/candidate" not in reply.text


def test_patch_api_errors_are_sanitized_and_unconfigured_capability_fails_closed(patch_environment, monkeypatch, caplog):
    from backend.services.patches import PatchService
    env = patch_environment
    sample = env.build_patch()
    with TestClient(create_app(), base_url="http://localhost") as client:
        assert client.post("/api/patches", json=body(sample)).status_code == 503
    def failed(*args):
        raise RuntimeError("PRIVATE_PATCH_EXCEPTION")
    monkeypatch.setattr(PatchService, "create", failed)
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        reply = client.post("/api/patches", json=body(sample))
        assert reply.status_code == 500 and reply.json()["code"] == "internal_error"
        assert "PRIVATE_PATCH_EXCEPTION" not in reply.text + caplog.text
