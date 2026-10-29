import pytest
from scripts.release_preflight import assess, tool_version


@pytest.fixture
def observed():
    return {"versions": {"python": "3.11.9", "node": "24.16.0", "npm": "11.13.0"},
            "packages": {name: "test-version" for name in ("fastapi", "uvicorn", "pydantic", "PyYAML", "pytest-cov")},
            "frontend_missing_or_mismatched": [], "inputs": {"status": "consistent"}}


def test_preflight_never_claims_build_or_release_success(observed):
    result = assess(observed, "release")
    assert result["prerequisites_satisfied"]
    assert result["production_build_verified"] is result["release_verified"] is False


@pytest.mark.parametrize("defect", ["python", "node", "npm", "packages", "installation", "inputs"])
def test_release_prerequisites_fail_explicitly(observed, defect):
    if defect == "python": observed["versions"]["python"] = "3.14.3"
    if defect in {"node", "npm"}: observed["versions"][defect] = None
    if defect == "packages": observed["packages"]["pydantic"] = None
    if defect == "installation": observed["frontend_missing_or_mismatched"] = ["vite", "bin:tsc"]
    if defect == "inputs": observed["inputs"]["status"] = "invalid"
    result = assess(observed, "release")
    assert not result["prerequisites_satisfied"]
    assert all(check["remediation"] for check in result["checks"])


def test_backend_profile_does_not_require_frontend_or_optional_coverage(observed):
    observed["versions"].update(python="3.14.3", node=None, npm=None)
    observed["packages"]["pytest-cov"] = None
    observed["frontend_missing_or_mismatched"] = ["vite"]
    assert assess(observed, "backend")["prerequisites_satisfied"]
    assert not assess(observed, "ci-backend")["prerequisites_satisfied"]


def test_failed_version_probe_never_returns_exception_text(monkeypatch):
    def fail(*_args, **_kwargs): raise OSError("PRIVATE_TEST_DETAIL")
    monkeypatch.setattr("scripts.release_preflight.subprocess.run", fail)
    assert tool_version(["node", "--version"]) is None
