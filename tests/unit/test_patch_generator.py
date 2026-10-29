"""Narrow byte-preserving proposals; all optimization evidence stays test-only."""

import ast
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


def test_bom_mixed_newlines_and_multiple_edits_preserve_exact_proposed_bytes_and_ast(patch_environment, monkeypatch):
    # Unlike upstream's git-apply regression, inspect the actual in-memory bytes
    # behind literal-spans.v1. No patch is written or applied to the source.
    raw = (b'\xef\xbb\xbf# coding: utf-8\r\nfrom openai import OpenAI\nclient = OpenAI()\r\n'
           b'banner = "local/baseline"  # keep "local/baseline"\r\n'
           + 'label = "\u4e2d\U0001f600\u2028"; first = client.chat.completions.create(\r\n'.encode("utf-8")
           + b"\tmodel = 'local/baseline',\t messages=[])\n# unchanged \t \r\n"
           + 'label2 = "\u00e9"; second = client.chat.completions.create(model="local/baseline", messages=[]) # tail'.encode("utf-8"))
    expected = raw.replace(b"model = 'local/baseline'", b'model = "local/candidate"').replace(
        b'model="local/baseline"', b'model="local/candidate"')
    env = patch_environment
    sample = env.build_patch(raw)
    splice, observed = patch_generator._splice, []
    def capture(original, replacements):
        proposed = splice(original, replacements)
        observed.append((original, proposed))
        return proposed
    monkeypatch.setattr(patch_generator, "_splice", capture)
    first, second = sample.proposal(), sample.proposal()
    assert first == second and first.manifest.provenance == "test" and first.manifest.status == "proposed"
    assert first.manifest.patch_format == "literal-spans.v1" and first.review_diff.startswith("literal-spans.v1\n")
    assert observed == [(raw, expected), (raw, expected)]
    file = first.manifest.files[0]
    assert len(file.edits) == 2
    assert file.original_digest == hashlib.sha256(raw).hexdigest()
    assert file.proposed_digest == hashlib.sha256(expected).hexdigest()
    # Find spans independently in the raw bytes, including the original BOM,
    # physical newlines and multibyte characters, rather than reusing AST offsets.
    first_start = raw.index(b"model = 'local/baseline'") + len(b"model = ")
    second_start = raw.index(b'model="local/baseline"') + len(b"model=")
    assert [(edit.start_byte, edit.end_byte) for edit in file.edits] == [
        (first_start, first_start + len(b"'local/baseline'")),
        (second_start, second_start + len(b'"local/baseline"')),
    ]
    original_tree = ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 11))
    proposed_tree = ast.parse(observed[0][1].decode("utf-8-sig"), feature_version=(3, 11))
    changed = 0
    for node in ast.walk(original_tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create":
            literal = next(keyword.value for keyword in node.keywords if keyword.arg == "model")
            assert isinstance(literal, ast.Constant) and literal.value == "local/baseline"
            literal.value = "local/candidate"
            changed += 1
    assert changed == 2
    assert ast.dump(proposed_tree, include_attributes=False) == ast.dump(original_tree, include_attributes=False)
    assert (env.repository / "app.py").read_bytes() == raw


@pytest.mark.parametrize("change", ["lf_to_crlf", "crlf_to_lf", "add_bom", "remove_bom", "comment_byte", "model_literal"])
def test_newline_bom_or_literal_changes_invalidate_original_source_evidence(patch_environment, change):
    raw = b'from openai import OpenAI\nclient=OpenAI()\n# keep-this\nr=client.chat.completions.create(model="local/baseline", messages=[])\n'
    if change == "crlf_to_lf":
        raw = raw.replace(b"\n", b"\r\n")
    elif change == "remove_bom":
        raw = b"\xef\xbb\xbf" + raw
    env = patch_environment
    sample = env.build_patch(raw)
    original = sample.proposal()
    assert original.manifest.status == "proposed" and original.manifest.provenance == "test"
    changed = {"lf_to_crlf": lambda: raw.replace(b"\n", b"\r\n"),
               "crlf_to_lf": lambda: raw.replace(b"\r\n", b"\n"),
               "add_bom": lambda: b"\xef\xbb\xbf" + raw,
               "remove_bom": lambda: raw[3:],
               "comment_byte": lambda: raw.replace(b"keep-this", b"keep-that"),
               "model_literal": lambda: raw.replace(b"local/baseline", b"local/modified")}[change]()
    assert changed != raw
    if change != "model_literal":
        assert ast.dump(ast.parse(raw.decode("utf-8-sig")), include_attributes=False) == ast.dump(
            ast.parse(changed.decode("utf-8-sig")), include_attributes=False)
    # Simulate an external edit before generation, never a transformer write.
    path = env.repository / "app.py"
    path.write_bytes(changed)
    with pytest.raises(ServiceError) as error:
        sample.proposal(persist=True)
    assert error.value.code == "source_conflict"
    assert path.read_bytes() == changed
    assert env.storage.get_source_manifest(sample.analysis.analysis_id) == sample.manifest
    assert sample.manifest.files[0].sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ServiceError) as missing:
        env.storage.get_patch(original.manifest.patch_id)
    assert missing.value.code == "not_found"
