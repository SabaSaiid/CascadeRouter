"""Stored-span validation exercises actual schemas and scanner-confirmed ASTs."""

import hashlib

import pytest

from backend.compiler import patch_generator
from backend.compiler.ast_scanner import ScannerOptions, _scan_repository_with_sources
from backend.compiler.patch_validator import validate_file


def inputs(sample):
    parsed = []
    env = sample.environment
    with env.access.authorize(str(env.repository)):
        _scan_repository_with_sources(str(env.repository), ScannerOptions(), parsed.append)
    return parsed[0], sample.analysis.nodes, sample.record.response.result.decisions


@pytest.mark.parametrize("prefix,newline,tail", [(b"", b"\n", b"\n"), (b"", b"\r\n", b""),
                                               (b"\xef\xbb\xbf", b"\r\n", b"\r\n")])
def test_stored_multiple_spans_rebuild_exact_candidate_without_mutating_source(patch_environment, prefix, newline, tail):
    raw = prefix + newline.join([b'from openai import OpenAI', b'client = OpenAI()',
        'label = "\u4e2d\U0001f600"; one = client.chat.completions.create(model="local/baseline", messages=[])'.encode(),
        b'two = client.chat.completions.create(model="local/baseline", messages=[]) # tail']) + tail
    sample = patch_environment.build_patch(raw)
    proposal = sample.proposal()
    parsed, nodes, decisions = inputs(sample)
    result, generated = validate_file(parsed, proposal.manifest.files[0], nodes, decisions)
    expected = raw.replace(b'model="local/baseline"', b'model="local/candidate"')
    assert result.reason == "checked" and result.syntax == "passed" and result.ast_preservation == "verified"
    assert result.candidate_digest == hashlib.sha256(expected).hexdigest()
    assert generated.file == proposal.manifest.files[0]
    assert (result, generated) == validate_file(parsed, proposal.manifest.files[0], nodes, decisions)
    assert (patch_environment.repository / "app.py").read_bytes() == raw
    assert proposal.manifest.provenance == "test"


@pytest.mark.parametrize("change", ["negative", "empty", "out_of_range", "offset", "old_text", "unapproved", "empty_model", "path", "duplicate", "overlap", "reversed"])
def test_invalid_stored_spans_are_rejected_before_candidate_construction(patch_environment, monkeypatch, change):
    raw = (b'from openai import OpenAI\nclient = OpenAI()\n'
           b'one = client.chat.completions.create(model="local/baseline", messages=[])\n'
           b'two = client.chat.completions.create(model="local/baseline", messages=[])\n')
    sample = patch_environment.build_patch(raw)
    proposal = sample.proposal()
    parsed, nodes, decisions = inputs(sample)
    data = proposal.manifest.files[0].model_dump(mode="json")
    first, second = data["edits"]
    if change == "negative": first["start_byte"] = -1
    elif change == "empty": first["end_byte"] = first["start_byte"]
    elif change == "out_of_range": second["end_byte"] = len(raw) + 1
    elif change == "offset": first["start_byte"] += 1
    elif change == "old_text": first["old_model_id"] = "stale/model"
    elif change == "unapproved": first["proposed_model_id"] = "unapproved/model"
    elif change == "empty_model": first["proposed_model_id"] = ""
    elif change == "path": data["file_path"] = "../outside.py"
    elif change == "duplicate": second["node_id"] = first["node_id"]
    elif change == "overlap": second["start_byte"] = first["start_byte"] + 1
    else: data["edits"].reverse()
    monkeypatch.setattr(patch_generator, "_splice", lambda *_: pytest.fail("Invalid spans reached construction."))
    result, generated = validate_file(parsed, data, nodes, decisions)
    assert result.reason == "invalid_spans" and result.candidate == result.syntax == "not_checked"
    assert result.candidate_digest is None and generated is None
    assert (patch_environment.repository / "app.py").read_bytes() == raw


def test_wrong_candidate_digest_is_rejected_before_syntax_check(patch_environment, monkeypatch):
    sample = patch_environment.build_patch()
    proposal = sample.proposal()
    parsed, nodes, decisions = inputs(sample)
    data = {**proposal.manifest.files[0].model_dump(), "proposed_digest": "0" * 64}
    monkeypatch.setattr(patch_generator, "_parse_candidate", lambda *_: pytest.fail("Mismatched candidate was parsed."))
    result, generated = validate_file(parsed, data, nodes, decisions)
    assert result.reason == "candidate_digest_mismatch" and result.candidate == "constructed"
    assert result.syntax == "not_checked" and generated is None
