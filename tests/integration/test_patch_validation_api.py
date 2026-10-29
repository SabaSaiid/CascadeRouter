"""Transport fixtures inject actual test reports, never production approvals."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.config import BackendConfig
from backend.main import create_app
from backend.schemas import PatchProposal, PatchValidationReport
from backend.services.patches import PatchService


@pytest.mark.parametrize("state", ["validated", "partial", "invalid", "stale", "unavailable"])
def test_validation_transport_preserves_real_static_outcomes_and_redacts_source(validation_environment, monkeypatch, state):
    env = validation_environment
    raw = None
    if state in ("partial", "unavailable"):
        raw = b'from openai import OpenAI\nclient = OpenAI()\n'
        if state == "partial":
            raw += b'one = client.chat.completions.create(model="local/baseline", messages=[])\n'
        raw += b'two = client.chat.completions.create(model=MODEL, messages=[])\n'
    sample = env.build_patch(raw)
    proposal = sample.proposal()
    if state == "invalid":
        data = proposal.model_dump(mode="json")
        data["review_diff"] += "# noncanonical artifact\n"
        data["artifact_digest"] = hashlib.sha256(data["review_diff"].encode()).hexdigest()
        data.pop("digest")
        data["digest"] = hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        proposal = PatchProposal.model_validate(data)
    env.storage.save_patch(proposal)
    if state == "stale":
        (env.repository / "app.py").write_bytes(sample.raw + b"# stale\n")
    report = env.validation_report(sample, proposal)
    assert report.result.status == state and report.result.provenance == "test"
    env.storage.save_validation(report)

    # Exercise serialization/transport only. Production authorization is not
    # replaced or enabled by any application configuration or test benchmark flag.
    def evaluated_test_report(self, patch_id, check):
        check()
        assert patch_id == report.result.patch_id
        return report
    monkeypatch.setattr(PatchService, "validate", evaluated_test_report)
    before = (env.repository / "app.py").read_bytes()
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/patches/" + proposal.manifest.patch_id + "/validate", json={})
        assert response.status_code == 201
        assert PatchValidationReport.model_validate(response.json()) == report
        assert "request_body" not in response.json()
        assert all(value not in response.text for value in (str(env.repository), env.repository.as_posix(), "PRIVATE_", "literal-spans.v1"))
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/patches/{patch_id}/validate"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("PatchValidationReport")
    assert (env.repository / "app.py").read_bytes() == before
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal


def test_production_validation_rejects_test_proposals_and_persists_no_report(validation_environment):
    env = validation_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    with TestClient(create_app(env.settings, benchmark_registry=sample.sample.registry,
                               benchmark_executor=sample.sample.executor, allow_test_benchmarks=True), base_url="http://localhost") as client:
        response = client.post("/api/patches/" + proposal.manifest.patch_id + "/validate")
        assert response.status_code == 503 and response.json()["code"] == "capability_unavailable"
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal
    import sqlite3
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM patch_validations").fetchone()[0] == 0


@pytest.mark.parametrize("body", [{"source": "PRIVATE"}, {"command": "PRIVATE"}, {"apply": True},
                                  {"repository_path": "../PRIVATE"}, {"spans": []}, "PRIVATE"])
def test_validation_accepts_no_caller_source_paths_commands_or_spans(validation_environment, monkeypatch, body):
    env = validation_environment
    monkeypatch.setattr(PatchService, "validate", lambda *_: pytest.fail("Invalid input reached validation."))
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/patches/patch_" + "a" * 32 + "/validate", json=body)
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
        assert "PRIVATE" not in response.text


def test_validation_missing_ids_unconfigured_service_and_current_scope(validation_environment, tmp_path):
    env = validation_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    path = "/api/patches/" + proposal.manifest.patch_id + "/validate"
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        assert client.post("/api/patches/patch_" + "0" * 32 + "/validate").status_code == 404
        assert client.post("/api/patches/invalid/validate").status_code == 422
        assert client.post(path + "?source=PRIVATE").status_code == 422
    with TestClient(create_app(), base_url="http://localhost") as client:
        assert client.post(path).status_code == 503
    other = tmp_path / "other"
    other.mkdir()
    settings = BackendConfig(permitted_repository_roots=[other], storage_directory=env.directory)
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        response = client.post(path)
        assert response.status_code == 403 and response.json()["code"] == "repository_forbidden"


def test_validation_internal_errors_are_sanitized(validation_environment, monkeypatch, caplog):
    env = validation_environment
    def failed(*_):
        raise RuntimeError("PRIVATE_VALIDATOR_FAILURE")
    monkeypatch.setattr(PatchService, "validate", failed)
    with TestClient(create_app(env.settings), base_url="http://localhost") as client:
        response = client.post("/api/patches/patch_" + "a" * 32 + "/validate")
        assert response.status_code == 500 and response.json()["code"] == "internal_error"
        assert "PRIVATE" not in response.text + caplog.text
