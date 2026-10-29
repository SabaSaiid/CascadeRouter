import os
import textwrap
from pathlib import Path

import pytest

from backend.compiler.ast_scanner import (
    DYNAMIC_MODEL,
    UNSPECIFIED_MODEL,
    ScanPathError,
    resolve_scan_path,
    scan_repository,
)
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def _write(root: Path, rel: str, code: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code))


def _by_id(scan):
    return {c.node_id: c for c in scan.calls}


# ------------------------------------------------------------- sample repo


def test_sample_repo_nodes():
    scan = scan_repository(SAMPLE)
    nodes = _by_id(scan)
    assert list(nodes) == [
        "node_classify_customer_intent",
        "node_extract_ticket_metadata",
        "node_generate_support_resolution",
    ]
    assert scan.scanned_files_count == 2  # agent/__init__.py + agent/workflow.py; tests/ skipped
    assert scan.detected_framework == "OpenAI SDK"
    assert scan.warnings == []

    classify = nodes["node_classify_customer_intent"]
    assert classify.file_path == "agent/workflow.py"
    assert classify.current_model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert classify.model_is_literal is True
    assert classify.prompt_reference == "SYSTEM_INTENT_CLASSIFICATION_PROMPT"
    assert classify.expected_schema["required"] == ["category", "confidence"]
    assert classify.json_required is True
    assert classify.docstring.startswith("Classifies customer inquiry")
    assert classify.snippet.startswith("response = client.chat.completions.create(")
    source_lines = (SAMPLE / "agent/workflow.py").read_text().splitlines()
    assert source_lines[classify.line_number - 1].strip().startswith("response = client.chat")

    extract = nodes["node_extract_ticket_metadata"]
    assert extract.current_model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert extract.model_is_literal is False  # resolved through ULTRA_MODEL constant
    assert extract.prompt_reference == "ENTITY_EXTRACTION_PROMPT"  # via local f-string
    assert extract.expected_schema["required"] == ["account_id"]
    assert "response_format" in extract.kwargs

    synth = nodes["node_generate_support_resolution"]
    assert synth.prompt_reference == "RESOLUTION_SYNTHESIS_TEMPLATE"  # via history list
    assert synth.expected_schema is None and synth.json_required is False
    assert synth.max_tokens == 1024


def test_to_llm_node_matches_schema():
    node = scan_repository(SAMPLE).calls[0].to_llm_node()
    dumped = node.model_dump()
    assert dumped["node_id"] == "node_classify_customer_intent"
    assert dumped["call_signature"] == "client.chat.completions.create(model=..., messages=[...], temperature=...)"


# ------------------------------------------------------------- detection rules


def test_detects_variants_and_ignores_non_llm_calls(tmp_path):
    _write(tmp_path, "app.py", '''
        import openai
        MODEL = "m-const"
        def a(c):
            return c.chat.completions.create(model="m1", messages=[])
        async def b(c, name):
            return await c.responses.create(model=name, input="hi")
        def d(c):
            c.completions.create(prompt="x")
        def not_llm(c):
            c.files.create(x=1)
            create(model="nope")
        top = openai.chat.completions.create(model=MODEL, messages=[])
    ''')
    nodes = _by_id(scan_repository(tmp_path))
    assert set(nodes) == {"node_a", "node_b", "node_d", "node_app_l13"}
    assert nodes["node_a"].current_model == "m1"
    assert nodes["node_b"].current_model == DYNAMIC_MODEL
    assert nodes["node_d"].current_model == UNSPECIFIED_MODEL
    assert nodes["node_app_l13"].current_model == "m-const"
    assert nodes["node_app_l13"].function_name is None


def test_duplicate_node_ids_are_suffixed(tmp_path):
    _write(tmp_path, "a.py", '''
        def f(c):
            c.chat.completions.create(model="x", messages=[])
            c.chat.completions.create(model="y", messages=[])
    ''')
    _write(tmp_path, "b.py", '''
        def f(c):
            c.chat.completions.create(model="z", messages=[])
        def f_2(c):
            c.chat.completions.create(model="w", messages=[])
    ''')
    ids = [c.node_id for c in scan_repository(tmp_path).calls]
    assert ids == ["node_f", "node_f_2", "node_f_3", "node_f_2_2"]
    assert len(set(ids)) == len(ids)


def test_inline_json_schema_response_format(tmp_path):
    _write(tmp_path, "s.py", '''
        def f(c):
            return c.chat.completions.create(
                model="x", messages=[],
                response_format={"type": "json_schema", "json_schema": {"name": "n", "schema": {"type": "object", "required": ["k"]}}},
            )
    ''')
    call = scan_repository(tmp_path).calls[0]
    assert call.expected_schema == {"type": "object", "required": ["k"]}
    assert call.json_required


def test_schema_referenced_in_function_wins_over_name_match(tmp_path):
    _write(tmp_path, "s.py", '''
        FOO_SCHEMA = {"type": "object", "required": ["foo"]}
        BAR_SCHEMA = {"type": "object", "required": ["bar"]}
        def foo_step(c):
            r = c.chat.completions.create(model="x", messages=[])
            validate(r, BAR_SCHEMA)
    ''')
    assert scan_repository(tmp_path).calls[0].expected_schema["required"] == ["bar"]


def test_no_schema_when_nothing_matches(tmp_path):
    _write(tmp_path, "s.py", '''
        OTHER_SCHEMA = {"type": "object"}
        def summarize(c):
            return c.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
    ''')
    call = scan_repository(tmp_path).calls[0]
    assert call.expected_schema is None and call.prompt_reference is None and not call.json_required


def test_never_executes_target_code(tmp_path):
    marker = tmp_path / "executed"
    _write(tmp_path, "evil.py", f'''
        open({str(marker)!r}, "w").write("pwned")
        def f(c):
            c.chat.completions.create(model="x", messages=[])
    ''')
    assert len(scan_repository(tmp_path).calls) == 1
    assert not marker.exists()


def test_skips_bad_files_and_dirs(tmp_path):
    _write(tmp_path, "broken.py", "def (:\n")
    _write(tmp_path, "venv/lib.py", 'c.chat.completions.create(model="x")')
    _write(tmp_path, "tests/test_x.py", 'c.chat.completions.create(model="x")')
    _write(tmp_path, "test_top.py", 'c.chat.completions.create(model="x")')
    _write(tmp_path, ".hidden/h.py", 'c.chat.completions.create(model="x")')
    (tmp_path / "latin.py").write_bytes(b"x = '\xff'\n")
    _write(tmp_path, "ok.py", "import litellm\nimport langchain_openai.chat\n")
    scan = scan_repository(tmp_path)
    assert scan.calls == []
    assert scan.scanned_files_count == 1
    assert scan.detected_framework == "LiteLLM / LangChain"
    assert any("broken.py" in w for w in scan.warnings)
    assert any("latin.py" in w for w in scan.warnings)


def test_symlinked_files_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    _write(outside, "secret.py", 'c.chat.completions.create(model="x")')
    repo = tmp_path / "repo"
    repo.mkdir()
    os.symlink(outside / "secret.py", repo / "link.py")
    os.symlink(outside, repo / "linkdir")
    assert scan_repository(repo).calls == []


def test_large_file_is_skipped(tmp_path, monkeypatch):
    import backend.compiler.ast_scanner as mod

    monkeypatch.setattr(mod, "MAX_FILE_BYTES", 10)
    _write(tmp_path, "big.py", "x = 1  # long enough\n")
    scan = scan_repository(tmp_path)
    assert scan.scanned_files_count == 0 and "larger than 2 MB" in scan.warnings[0]


def test_file_cap(tmp_path, monkeypatch):
    import backend.compiler.ast_scanner as mod

    monkeypatch.setattr(mod, "MAX_FILES", 2)
    for i in range(4):
        _write(tmp_path, f"m{i}.py", "x = 1\n")
    scan = scan_repository(tmp_path)
    assert scan.scanned_files_count == 2 and scan.warnings == ["Stopped after 2 files"]


# ------------------------------------------------------------- path safety


def test_resolve_scan_path_relative_and_absolute():
    assert resolve_scan_path("tests/fixtures/sample_repo", [REPO_ROOT], REPO_ROOT) == SAMPLE
    assert resolve_scan_path(str(SAMPLE), [REPO_ROOT], REPO_ROOT) == SAMPLE
    assert resolve_scan_path(".", [REPO_ROOT], REPO_ROOT) == REPO_ROOT


@pytest.mark.parametrize("raw", ["", "../", "/etc", "tests/../../", "a\x00b", "does/not/exist"])
def test_resolve_scan_path_rejects(raw):
    with pytest.raises(ScanPathError):
        resolve_scan_path(raw, [REPO_ROOT], REPO_ROOT)


def test_resolve_scan_path_rejects_symlink_and_file(tmp_path):
    (tmp_path / "real").mkdir()
    os.symlink(tmp_path / "real", tmp_path / "link")
    (tmp_path / "f.py").write_text("")
    roots = [tmp_path.resolve()]
    with pytest.raises(ScanPathError, match="symlink"):
        resolve_scan_path("link", roots, tmp_path)
    with pytest.raises(ScanPathError, match="not a directory"):
        resolve_scan_path("f.py", roots, tmp_path)
    with pytest.raises(ScanPathError, match="outside"):
        resolve_scan_path(str(tmp_path.parent), roots, tmp_path)
