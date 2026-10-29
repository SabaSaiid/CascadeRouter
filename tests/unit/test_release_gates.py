import copy
import json
import pytest
from scripts.release_gates import REGISTER, REQUIRED, validate


def register():
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def test_current_register_is_complete_and_explicitly_blocks_release():
    result = validate(register())
    assert result["valid"] and result["pending_required"]
    assert result["recommendation"] == "blocked_from_release"


@pytest.mark.parametrize("defect,code", [("missing", "gate_inventory_mismatch"), ("duplicate", "gate_inventory_mismatch"),
    ("unsupported_pass", "unsupported_pass"), ("escape", "invalid_evidence_reference"),
    ("waiver", "required_gate_cannot_be_waived"), ("optionalize", "required_gate_cannot_be_waived"), ("ready", "recommendation_mismatch")])
def test_register_cannot_hide_missing_requirements_or_evidence(defect, code):
    value = register()
    if defect == "missing": value["gates"].pop()
    if defect == "duplicate": value["gates"].append(copy.deepcopy(value["gates"][0]))
    if defect == "unsupported_pass": value["gates"][0].update(status="passed", actual=None)
    if defect == "escape": value["gates"][0]["evidence"][0]["path"] = "../outside.md"
    if defect == "waiver": value["gates"][0]["status"] = "not applicable"
    if defect == "optionalize": value["gates"][0]["required"] = False
    if defect == "ready": value["recommendation"] = "ready_for_controlled_candidate_build"
    assert code in validate(value)["errors"]


def test_all_required_gate_ids_remain_explicit():
    assert len(REQUIRED) == 15
