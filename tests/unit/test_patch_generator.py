"""Narrow byte-preserving proposals; all optimization evidence stays test-only."""

import hashlib
from pathlib import Path

import pytest

from backend.compiler import patch_generator
from backend.compiler.patch_generator import PatchInputError, _splice
from backend.services.errors import ServiceError


def test_literal_change_is_deterministic_sensitive_context_free_and_never_applied(patch_environment):
    env = patch_environment
    raw = b'from openai import OpenAI\nclient = OpenAI()\nresult = client.chat.completions.create(model="local/baseline", messages=[{"content":"PRIVATE_PROMPT"}], api_key="PRIVATE_CREDENTIAL")\n'
    sample = env.build_patch(raw)
    first, second = sample.proposal(), sample.proposal()
    expected = raw.replace(b'"local/baseline"', b'"local/candidate"')
    assert first == second and first.manifest.status == "proposed"
    assert first.manifest.provenance == "test" and first.manifest.complete_for_requested_nodes
    assert first.manifest.files[0].proposed_digest == hashlib.sha256(expected).hexdigest()
    assert first.review_diff.startswith("literal-spans.v1\n")
    assert '"local/candidate"' in first.review_diff and "PRIVATE" not in first.model_dump_json()
    assert (env.repository / "app.py").read_bytes() == raw


@pytest.mark.parametrize("prefix,newline,literal", [(b"", b"\n", b'"local/baseline"'), (b"\xef\xbb\xbf", b"\r\n", b"'local/baseline'"),
                                                  (b"", b"\r", b'u"local/baseline"'), (b"", b"\r\n", b'r"local/baseline"')])
def test_bom_newlines_unicode_and_literal_prefixes_preserve_unrelated_bytes(patch_environment, prefix, newline, literal):
    env = patch_environment
    raw = prefix + newline.join([b"from openai import OpenAI", b"client = OpenAI()",
        'label = "\u4e2d\u6587\U0001f600\u2028"; response = client.chat.completions.create(model='.encode("utf-8") + literal + b", messages=[]) # comment", b""])
    sample = env.build_patch(raw)
    item = sample.proposal()
    assert item.manifest.status == "proposed"
    expected = raw.replace(literal, b'"local/candidate"')
    assert item.manifest.files[0].proposed_digest == hashlib.sha256(expected).hexdigest()
    edit = item.manifest.files[0].edits[0]
    assert raw[edit.start_byte:edit.end_byte] == literal
    assert (env.repository / "app.py").read_bytes() == raw


def test_retained_baseline_has_explicit_no_change_status(patch_environment):
    sample = patch_environment.build_patch(rates={"local/baseline": "1", "local/candidate": "2"})
    item = sample.proposal()
    assert item.manifest.status == "unavailable" and not item.manifest.complete_for_requested_nodes
    assert item.review_diff == "" and item.manifest.files == ()
    assert item.manifest.omissions[0].reason == "baseline_retained"


@pytest.mark.parametrize("expression,reason", [("MODEL", "model_unresolved"), ("'local/' 'baseline'", "unsupported_literal"),
                                             ('"""local/baseline"""', "unsupported_literal"), ('"other/model"', "baseline_mismatch")])
def test_dynamic_and_unsupported_literals_are_omitted(patch_environment, expression, reason):
    raw = ('from openai import OpenAI\nclient = OpenAI()\nresponse = client.chat.completions.create(model=' + expression + ', messages=[])\n').encode()
    item = patch_environment.build_patch(raw).proposal()
    assert item.manifest.status == "unavailable" and item.review_diff == ""
    assert item.manifest.omissions[0].reason == reason


def test_unsupported_source_encoding_is_explicitly_omitted(patch_environment):
    raw = '# coding: latin-1\nfrom openai import OpenAI\nclient = OpenAI()\nlabel="\u00e9"\nresponse = client.chat.completions.create(model="local/baseline", messages=[])\n'.encode("latin-1")
    item = patch_environment.build_patch(raw).proposal()
    assert item.manifest.status == "unavailable" and item.manifest.omissions[0].reason == "unsupported_encoding"


def test_multiple_edits_on_one_line_and_unsupported_sdk_call_are_preserved(patch_environment):
    raw = b'from openai import OpenAI\nclient = OpenAI()\nunsupported = client.responses.create(model="local/baseline")\na=client.chat.completions.create(model="local/baseline", messages=[]); b=client.chat.completions.create(model="local/baseline", messages=[])\n'
    item = patch_environment.build_patch(raw).proposal()
    assert len(item.manifest.files[0].edits) == 2
    expected = raw.replace(b'model="local/baseline", messages', b'model="local/candidate", messages')
    assert item.manifest.files[0].proposed_digest == hashlib.sha256(expected).hexdigest()
    assert "responses" not in item.review_diff


def test_partial_proposal_does_not_claim_dynamic_node_was_changed(patch_environment):
    raw = b'from openai import OpenAI\nclient = OpenAI()\na=client.chat.completions.create(model="local/baseline", messages=[])\nb=client.chat.completions.create(model=MODEL, messages=[])\n'
    item = patch_environment.build_patch(raw).proposal()
    assert item.manifest.status == "partial" and not item.manifest.complete_for_requested_nodes
    assert len(item.manifest.files[0].edits) == len(item.manifest.omissions) == 1


def test_unknown_node_is_rejected_without_source_changes(patch_environment):
    sample = patch_environment.build_patch()
    with pytest.raises(ServiceError) as error:
        sample.proposal(nodes=("llm_" + "0" * 24,))
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("ranges", [[(1, 4, b"x"), (3, 5, b"y")], [(1, 4, b"x"), (0, 1, b"y")], [(-1, 1, b"x")], [(0, 99, b"x")]])
def test_overlap_or_invalid_ranges_are_rejected(ranges):
    with pytest.raises(PatchInputError):
        _splice(b"abcdef", ranges)


def test_unapproved_comment_or_ast_change_is_rejected(patch_environment, monkeypatch):
    sample = patch_environment.build_patch()
    original = patch_generator._splice
    monkeypatch.setattr(patch_generator, "_splice", lambda *args: original(*args) + b"# unauthorized change\n")
    with pytest.raises(ServiceError) as error:
        sample.proposal()
    assert error.value.code == "source_conflict"


def test_proposal_generator_has_no_io_network_execution_or_import_discovery():
    import ast
    path = Path(__file__).parents[2] / "backend" / "compiler" / "patch_generator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in {"subprocess", "requests", "httpx", "socket", "importlib", "openai", "nebius", "tavily"} for alias in node.names)
