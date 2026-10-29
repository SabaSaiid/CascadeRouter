"""Differential evidence cases must actually violate the authoritative Pydantic contract."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from backend.schemas import JobResponse

FIXTURES = Path(__file__).resolve().parents[2] / "frontend/tests/fixtures"
VECTORS = json.loads((FIXTURES / "invalid-job-patches.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS, ids=lambda case: case["name"])
def test_client_negative_job_vectors_are_rejected_by_backend(case):
    value = json.loads((FIXTURES / "job.json").read_text(encoding="utf-8"))
    JobResponse.model_validate_json(json.dumps(value))
    for path, replacement in case["edits"]:
        parent = value
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = copy.deepcopy(replacement)
    with pytest.raises(ValidationError):
        JobResponse.model_validate_json(json.dumps(value))
