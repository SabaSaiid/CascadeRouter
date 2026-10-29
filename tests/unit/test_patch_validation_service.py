"""Internal tests retain test provenance; the production entry point rejects it."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.compiler import patch_generator
from backend.config import BackendConfig
from backend.schemas import PatchProposal
from backend.services.errors import ServiceError
from backend.services.patches import PatchService
from backend.services.repository_access import RepositoryAccess


def validate(sample, proposal=None, manifest=True):
    return sample.service._validate(proposal or sample.proposal(), sample.analysis,
                                    sample.manifest if manifest else None, sample.record)


def test_static_service_verifies_sources_deterministically_without_altering_artifacts(patch_environment):
    sample = patch_environment.build_patch()
    proposal = sample.proposal(persist=True)
    original = proposal.model_dump_json()
    result = validate(sample, proposal)
    assert result.status == "validated" and result.complete and result.source_identity == "verified"
    assert result == validate(sample, proposal) and result.provenance == "test"
    assert result.proposal_digest == proposal.digest and result.source_manifest_digest == sample.manifest.digest
    assert patch_environment.storage.get_patch(proposal.manifest.patch_id).model_dump_json() == original
    assert (patch_environment.repository / "app.py").read_bytes() == sample.raw
    with pytest.raises(ServiceError) as error:
        sample.service.validate(proposal.manifest.patch_id)
    assert error.value.code == "capability_unavailable"


@pytest.mark.parametrize("change", ["content", "newline", "bom", "encoding", "replacement", "missing"])
def test_static_service_rejects_changed_or_replaced_sources(patch_environment, change):
    sample = patch_environment.build_patch()
    proposal = sample.proposal(persist=True)
    path = patch_environment.repository / "app.py"
    if change == "content": path.write_bytes(sample.raw + b"# changed\n")
    elif change == "newline": path.write_bytes(sample.raw.replace(b"\n", b"\r\n"))
    elif change == "bom": path.write_bytes(b"\xef\xbb\xbf" + sample.raw)
    elif change == "encoding": path.write_bytes(b"# coding: latin-1\n" + sample.raw)
    elif change == "replacement":
        path.rename(path.with_suffix(".old"))
        path.write_bytes(sample.raw)
    else: path.unlink()
    before = path.read_bytes() if path.exists() else None
    result = validate(sample, proposal)
    assert result.status == "stale" and result.reason == "source_changed" and not result.complete
    assert result.files == () and result.source_identity == "stale"
    assert (path.read_bytes() if path.exists() else None) == before
    assert patch_environment.storage.get_patch(proposal.manifest.patch_id) == proposal


def test_missing_source_evidence_is_unavailable_without_reading_paths(patch_environment, monkeypatch):
    sample = patch_environment.build_patch()
    proposal = sample.proposal()
    monkeypatch.setattr("backend.services.patches.verify_sources", lambda *_args, **_kw: pytest.fail("Missing evidence triggered a read."))
    result = validate(sample, proposal, manifest=False)
    assert result.status == "unavailable" and result.reason == "source_evidence_unavailable"
    assert result.source_identity == "not_verified" and result.files == ()


def test_current_repository_policy_still_denies_validation(patch_environment, tmp_path):
    sample = patch_environment.build_patch()
    proposal = sample.proposal()
    other = tmp_path / "other"
    other.mkdir()
    settings = BackendConfig(permitted_repository_roots=[other], storage_directory=patch_environment.directory)
    service = PatchService(settings, SimpleNamespace(storage=patch_environment.storage, access=RepositoryAccess(settings)), None)
    with pytest.raises(ServiceError) as error:
        service._validate(proposal, sample.analysis, sample.manifest, sample.record)
    assert error.value.code == "repository_forbidden"


def test_syntax_failure_has_bounded_diagnostic_and_never_claims_success(patch_environment, monkeypatch):
    sample = patch_environment.build_patch()
    proposal = sample.proposal(persist=True)
    def failed(_):
        raise SyntaxError("PRIVATE_PARSER_TEXT", ("PRIVATE_HOST_PATH", 4, 2, "PRIVATE_SOURCE"))
    monkeypatch.setattr(patch_generator, "_parse_candidate", failed)
    result = validate(sample, proposal)
    assert result.status == "invalid" and result.files[0].syntax == "failed"
    assert result.files[0].diagnostic.line_number == 4
    assert "PRIVATE" not in result.model_dump_json()
    assert patch_environment.storage.get_patch(proposal.manifest.patch_id) == proposal
    assert (patch_environment.repository / "app.py").read_bytes() == sample.raw


def test_self_hashed_but_noncanonical_review_artifact_is_invalid(patch_environment):
    sample = patch_environment.build_patch()
    data = sample.proposal().model_dump(mode="json")
    data["review_diff"] += "# unrelated review change\n"
    data["artifact_digest"] = hashlib.sha256(data["review_diff"].encode()).hexdigest()
    data.pop("digest")
    data["digest"] = hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    proposal = PatchProposal.model_validate(data)
    result = validate(sample, proposal)
    assert result.status == "invalid" and result.reason == "proposal_mismatch" and result.structure == "invalid"
    assert result.source_identity == "verified" and not result.complete


def test_parser_budget_exhaustion_is_unavailable_rather_than_invalid(patch_environment, monkeypatch):
    sample = patch_environment.build_patch()
    proposal = sample.proposal()
    def limited(_):
        raise MemoryError("PRIVATE")
    monkeypatch.setattr(patch_generator, "_parse_candidate", limited)
    result = validate(sample, proposal)
    assert result.status == "unavailable" and result.reason == "file_validation_unavailable"
    assert result.source_identity == "verified" and result.files[0].reason == "resource_limit"
    assert result.files[0].syntax == "not_checked" and not result.complete


@pytest.mark.parametrize("partial", [False, True])
def test_omitted_nodes_are_not_reported_as_fully_validated(patch_environment, partial):
    raw = b'from openai import OpenAI\nclient = OpenAI()\n'
    if partial:
        raw += b'one = client.chat.completions.create(model="local/baseline", messages=[])\n'
    raw += b'two = client.chat.completions.create(model=MODEL, messages=[])\n'
    sample = patch_environment.build_patch(raw)
    result = validate(sample)
    assert result.status == ("partial" if partial else "unavailable") and not result.complete
    assert result.omitted_nodes == 1 and result.source_identity == "verified"
    assert result.reason == ("partial_proposal" if partial else "no_editable_files")
