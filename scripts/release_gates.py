"""Validate release evidence bookkeeping. Never executes gate commands."""
import argparse
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/release-gates.json"
REQUIRED = {"repository_tests", "frontend_tests", "typescript", "production_build", "lint", "browser_accessibility",
            "python311", "clean_dependencies", "local_api", "contracts", "security_integrity", "recovery",
            "production_evidence", "hosted_ci", "platform_filesystem"}
STATES = {"passed", "failed", "blocked", "not run", "not applicable"}


def validate(register, root=ROOT):
    errors = []
    if register.get("schema_version") != "cascaderouter.release-gates.v1" or register.get("version") is not None:
        errors.append("unsupported_register")
    gates = register.get("gates", [])
    ids = [gate.get("id") for gate in gates]
    if len(set(ids)) != len(ids) or set(ids) != REQUIRED:
        errors.append("gate_inventory_mismatch")
    for gate in gates:
        if (gate.get("status") not in STATES or type(gate.get("required")) is not bool
                or gate.get("severity") not in {"P1", "P2"}
                or any(not isinstance(gate.get(key), str) or not gate[key].strip()
                       for key in ("requirement", "expected", "impact", "remediation"))
                or not gate.get("procedure") or not all(isinstance(command, str) and command.strip() for command in gate["procedure"])
                or not isinstance(gate.get("environment"), dict) or not gate["environment"]):
            errors.append("invalid_gate_fields")
        if not gate.get("evidence"):
            errors.append("missing_evidence")
        for item in gate.get("evidence", []):
            path = item.get("path", "")
            relative = PurePosixPath(path)
            if (not path or "\\" in path or ":" in path or relative.is_absolute() or ".." in relative.parts
                    or not (root / path).is_file() or not (root / path).resolve().is_relative_to(root.resolve())
                    or not item.get("scope")):
                errors.append("invalid_evidence_reference")
        actual = gate.get("actual")
        if gate.get("status") == "passed" and (not isinstance(actual, dict) or type(actual.get("exit_code")) is not int or actual["exit_code"] != 0 or not actual.get("summary")):
            errors.append("unsupported_pass")
        if (gate.get("id") in REQUIRED and gate.get("required") is not True) or (gate.get("required") and gate.get("status") == "not applicable"):
            errors.append("required_gate_cannot_be_waived")
    pending = sorted(gate["id"] for gate in gates if gate.get("required") and gate.get("status") != "passed")
    recommendation = "blocked_from_release" if pending or errors else "ready_for_controlled_candidate_build"
    if register.get("recommendation") != recommendation:
        errors.append("recommendation_mismatch")
    return {"valid": not errors, "errors": sorted(set(errors)), "pending_required": pending, "recommendation": recommendation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready", action="store_true", help="Return nonzero for any unclosed required gate")
    args = parser.parse_args()
    try:
        result = validate(json.loads(REGISTER.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        result = {"valid": False, "errors": ["unreadable_register"]}
    print(json.dumps(result, sort_keys=True))
    return int(not result["valid"] or (args.require_ready and bool(result.get("pending_required"))))


if __name__ == "__main__":
    raise SystemExit(main())
