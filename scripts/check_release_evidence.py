"""Reconcile recorded release observations; does not run commands or authenticate evidence."""
import json
from pathlib import Path
from scripts.release_gates import ROOT, REGISTER, validate

OBSERVATIONS = ROOT / "docs/phase411-observations.json"


def check(register, observations):
    errors = list(validate(register)["errors"])
    if observations.get("schema_version") != "cascaderouter.release-observations.v1":
        errors.append("unsupported_observations")
    gates = {gate["id"]: gate for gate in register["gates"]}
    for name, key in (("repository_tests", "backend"), ("frontend_tests", "frontend")):
        counts = observations[key]
        if (set(counts) != {"tests", "passed", "failures", "errors", "skipped"}
                or any(type(value) is not int or value < 0 for value in counts.values())
                or counts["tests"] != sum(counts[k] for k in ("passed", "failures", "errors", "skipped"))
                or counts["passed"] == 0):
            errors.append("invalid_counts")
        if gates[name]["actual"].get("counts") != counts:
            errors.append("count_mismatch")
        if gates[name]["status"] == "passed" and (counts["failures"] or counts["errors"] or observations[key + "_exit_code"] != 0):
            errors.append("unsupported_test_pass")
    if observations["environment"]["python"].split(".")[:2] != ["3", "11"] and gates["python311"]["status"] == "passed":
        errors.append("unsupported_python311_pass")
    if observations["frontend_dependency_scope"] != "exact_lock":
        for name in ("typescript", "production_build", "lint"):
            if gates[name]["status"] == "passed": errors.append("supplemental_is_not_exact_lock")
    for name, key in (("browser_accessibility", "browser_executed"), ("hosted_ci", "hosted_ci_executed"),
                      ("clean_dependencies", "clean_environment_executed"), ("production_evidence", "genuine_production_evidence_available")):
        if observations[key] is not True and gates[name]["status"] == "passed":
            errors.append("unobserved_gate_pass")
    return {"consistent": not errors, "errors": sorted(set(errors)), "recommendation": register["recommendation"]}


def main():
    try:
        result = check(json.loads(REGISTER.read_text(encoding="utf-8")), json.loads(OBSERVATIONS.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result = {"consistent": False, "errors": ["evidence_unavailable"]}
    print(json.dumps(result, sort_keys=True))
    return int(not result["consistent"])


if __name__ == "__main__":
    raise SystemExit(main())
