"""Exercise the shared transient checker with trusted, test-only source strings."""

import ast
from types import SimpleNamespace

import pytest

from backend.compiler import patch_generator
from backend.compiler.patch_generator import PatchBudgetExceeded, PatchVerificationError, _verify_candidate
from backend.schemas import PatchEdit


def candidate_input():
    raw = b'raise RuntimeError("PRIVATE_NEVER_EXECUTED")\nmodel="local/baseline"\n'
    tree = ast.parse(raw.decode(), feature_version=(3, 11))
    literal = tree.body[1].value
    start = raw.index(b'"local/baseline"')
    edit = PatchEdit(node_id="llm_" + "a" * 24, old_model_id="local/baseline", proposed_model_id="local/candidate",
                     start_byte=start, end_byte=start + len(b'"local/baseline"'))
    parsed = SimpleNamespace(raw=raw, tree=tree, fingerprint=SimpleNamespace(file_path="app.py"))
    location = literal.lineno, literal.col_offset, literal.end_lineno, literal.end_col_offset
    return parsed, edit, location


def test_candidate_parsing_never_executes_and_does_not_mutate_original_ast():
    parsed, edit, location = candidate_input()
    before = ast.dump(parsed.tree, include_attributes=True)
    edits = [(edit, b'"local/candidate"', '"local/baseline"', location)]
    result = _verify_candidate(parsed, edits, "utf-8")
    assert result == parsed.raw.replace(b'"local/baseline"', b'"local/candidate"')
    assert result == _verify_candidate(parsed, edits, "utf-8")
    assert ast.dump(parsed.tree, include_attributes=True) == before


@pytest.mark.parametrize("replacement,reason,syntax", [(b"(", "syntax_error", "failed"),
    (b'"local/candidate"; unexpected()', "ast_mismatch", "passed")])
def test_actual_parser_and_ast_failures_are_reported_without_source_text(replacement, reason, syntax):
    parsed, edit, location = candidate_input()
    with pytest.raises(PatchVerificationError) as error:
        _verify_candidate(parsed, [(edit, replacement, "unused", location)], "utf-8")
    result = error.value.validation
    assert result.reason == reason and result.syntax == syntax and result.candidate == "constructed"
    assert "PRIVATE" not in result.model_dump_json() and "unexpected" not in str(error.value)
    if reason == "syntax_error":
        assert result.diagnostic.line_number == 2 and result.diagnostic.column_number is not None


@pytest.mark.parametrize("failure", [MemoryError, RecursionError])
def test_parser_resource_exhaustion_never_becomes_syntax_success(monkeypatch, failure):
    parsed, edit, location = candidate_input()
    def unavailable(*args):
        raise failure("PRIVATE")
    monkeypatch.setattr(patch_generator, "_parse_candidate", unavailable)
    with pytest.raises(PatchBudgetExceeded):
        _verify_candidate(parsed, [(edit, b'"local/candidate"', "unused", location)], "utf-8")


def test_candidate_size_limit_is_enforced_before_parsing(monkeypatch):
    parsed, edit, location = candidate_input()
    monkeypatch.setattr(patch_generator, "_parse_candidate", lambda *_: pytest.fail("Oversized candidate was parsed."))
    with pytest.raises(PatchBudgetExceeded):
        _verify_candidate(parsed, [(edit, b"x" * (1024 * 1024), "unused", location)], "utf-8")
