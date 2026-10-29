"""Static evidence is distinct from runtime success and never carries source text."""

import pytest
from pydantic import ValidationError

from backend.schemas import PatchFileValidation, PatchValidationReport, PatchValidationResult


def checked_file(**changes):
    return dict(file_path="app.py", original_digest="a" * 64, candidate_digest="b" * 64,
                spans="valid", candidate="constructed", syntax="passed", ast_preservation="verified", reason="checked", **changes)


def result_data():
    return dict(patch_id="patch_" + "a" * 32, proposal_digest="a" * 64, analysis_id="analysis_" + "a" * 32,
                source_manifest_digest="b" * 64, provenance="test", status="validated", reason="statically_validated",
                structure="valid", source_evidence="available", source_identity="verified", complete=True,
                omitted_nodes=0, files=[checked_file()])


def test_static_report_round_trip_binding_and_no_behavioral_claim():
    report = PatchValidationReport.create(checked_at="2026-10-29T00:00:00Z", python_version="3.14.3", result=result_data())
    assert PatchValidationReport.model_validate_json(report.model_dump_json()) == report
    assert report.result.provenance == "test" and "applied" not in report.model_dump_json()
    with pytest.raises(ValidationError):
        PatchValidationReport.model_validate({**report.model_dump(), "checked_at": "2026-10-30T00:00:00Z"})


@pytest.mark.parametrize("change", [
    {"status": "partial"}, {"complete": False}, {"source_identity": "not_verified"},
    {"source_evidence": "unavailable"}, {"structure": "invalid"}, {"files": []},
    {"omitted_nodes": 1}, {"files": [checked_file(), checked_file()]}, {"runtime_passed": True},
])
def test_static_success_cannot_claim_unperformed_or_inconsistent_checks(change):
    with pytest.raises(ValidationError):
        PatchValidationResult.model_validate({**result_data(), **change})


@pytest.mark.parametrize("change", [
    {"syntax": "not_checked"}, {"candidate_digest": None}, {"ast_preservation": "not_checked"},
    {"spans": "invalid"}, {"diagnostic": {"code": "candidate_syntax_error"}}, {"file_path": "../outside.py"},
])
def test_file_checks_are_consistent_and_paths_cannot_escape(change):
    with pytest.raises(ValidationError):
        PatchFileValidation.model_validate({**checked_file(), **change})


def test_partial_and_unavailable_states_do_not_claim_full_validation():
    partial = PatchValidationResult.model_validate({**result_data(), "status": "partial", "reason": "partial_proposal",
        "omitted_nodes": 1, "omissions": [{"node_id": "llm_" + "b" * 24, "reason": "unsupported_encoding"}], "complete": False})
    assert partial.files[0].syntax == "passed" and not partial.complete
    missing = PatchValidationResult.model_validate({**result_data(), "status": "unavailable", "reason": "source_evidence_unavailable",
        "source_evidence": "unavailable", "source_identity": "not_verified", "complete": False, "files": []})
    assert missing.files == ()
