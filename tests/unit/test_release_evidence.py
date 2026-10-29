"""Synthetic bookkeeping fixtures test reconciliation, never production/test claims."""
import json
import pytest
from scripts.release_gates import REGISTER
from scripts.check_release_evidence import check


@pytest.fixture
def records():
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    observed = {"schema_version": "cascaderouter.release-observations.v1", "environment": {"python": "3.14.3"},
                "frontend_dependency_scope": "supplemental", "backend_exit_code": 0, "frontend_exit_code": 0,
                "browser_executed": False, "hosted_ci_executed": False, "clean_environment_executed": False,
                "genuine_production_evidence_available": False}
    for name, key in (("repository_tests", "backend"), ("frontend_tests", "frontend")):
        # Test-only numeric fixture, detached from real observations.
        counts = dict(tests=2, passed=1, failures=0, errors=0, skipped=1)
        observed[key] = dict(counts)
        next(g for g in register["gates"] if g["id"] == name)["actual"]["counts"] = dict(counts)
    return register, observed


def test_consistent_local_evidence_does_not_close_unobserved_release_gates(records):
    result = check(*records)
    assert result["consistent"] and result["recommendation"] == "blocked_from_release"


@pytest.mark.parametrize("defect,code", [("counts", "count_mismatch"), ("zero", "invalid_counts"),
    ("failure", "unsupported_test_pass"), ("python311", "unsupported_python311_pass"),
    ("production_build", "supplemental_is_not_exact_lock"), ("browser_accessibility", "unobserved_gate_pass"),
    ("hosted_ci", "unobserved_gate_pass"), ("production_evidence", "unobserved_gate_pass")])
def test_unobserved_success_or_inconsistent_counts_are_rejected(records, defect, code):
    register, observed = records
    if defect == "counts": observed["backend"]["passed"] = 2
    elif defect == "zero": observed["backend"]["passed"] = 0
    elif defect == "failure": observed["backend_exit_code"] = 1
    else:
        gate = next(g for g in register["gates"] if g["id"] == defect)
        gate.update(status="passed", actual={"summary": "synthetic unsupported claim", "exit_code": 0})
    assert code in check(register, observed)["errors"]
