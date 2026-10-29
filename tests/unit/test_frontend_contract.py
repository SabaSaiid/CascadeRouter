"""Prevent frontend types/response validators drifting from the actual backend."""

from frontend.scripts.sync_contracts import ROOT, render_contract
import pytest
from backend import schemas
import json
from pydantic import ValidationError


def test_frontend_contract_matches_current_openapi():
    assert (ROOT / "frontend/src/services/contracts.ts").read_text(encoding="utf-8") == render_contract()


@pytest.mark.parametrize("filename, model", [
    ("health", schemas.HealthResponse), ("scan", schemas.ScanResponse),
    ("job", schemas.JobResponse), ("jobAccepted", schemas.JobAccepted),
    ("optimization", schemas.OptimizationResponse), ("patch", schemas.PatchProposal),
    ("optimizationUnavailable", schemas.OptimizationResponse),
    ("patchAccepted", schemas.PatchAccepted), ("validation", schemas.PatchValidationReport),
])
def test_frontend_test_fixtures_use_actual_pydantic_contracts(filename, model):
    value = model.model_validate_json((ROOT / f"frontend/tests/fixtures/{filename}.json").read_text(encoding="utf-8"))
    if filename == "scan":
        assert value.data_source == "mock"
    elif filename == "job":
        assert value.plan.provenance == "test"
    elif filename in {"optimization", "optimizationUnavailable", "validation"}:
        assert value.result.provenance == "test"
    elif filename == "patch":
        assert value.manifest.provenance == "test"


@pytest.mark.parametrize("key", ["constructor", "__proto__", "toString"])
def test_inherited_javascript_names_are_still_forbidden_backend_extra_fields(key):
    value = json.loads((ROOT / "frontend/tests/fixtures/health.json").read_text(encoding="utf-8"))
    value[key] = {}
    with pytest.raises(ValidationError):
        schemas.HealthResponse.model_validate_json(json.dumps(value))
