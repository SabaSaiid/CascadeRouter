"""Tests import the trusted scanner; scanned applications are source data only."""

from __future__ import annotations

import ast
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from backend.compiler import dag_builder
from backend.compiler.ast_scanner import ScanDiagnostic, ScannerOptions, scan_repository
from backend.compiler.dag_builder import (
    GraphOptions, ProvisionalAnalysisResult, analyze_repository, build_workflow_graph,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sample_repo"
PREAMBLE = "from openai import OpenAI\nclient = OpenAI()\n"
CALL = 'client.chat.completions.create(model="fixture/model", messages=messages)\n'


def source(tmp_path: Path, content: str, name: str = "app.py") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def codes(result) -> set[str]:
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_bundled_fixtures_are_parsed_not_imported():
    result = scan_repository(str(FIXTURES))
    assert result.complete
    assert result.discovered_files_count == result.scanned_files_count == 3
    assert len(result.nodes) == 4
    assert not result.diagnostics
    assert {node.file_path for node in result.nodes} == {
        "supported_sync.py", "supported_async.py",
    }
    assert result.total_source_bytes_read == sum(path.stat().st_size for path in FIXTURES.glob("*.py"))


def test_sync_locations_models_and_references():
    result = scan_repository(str(FIXTURES))
    nodes = [node for node in result.nodes if node.file_path == "supported_sync.py"]
    first, nested = nodes
    tree = ast.parse((FIXTURES / "supported_sync.py").read_text(encoding="utf-8"))
    call_lines = sorted(item.lineno for item in ast.walk(tree)
                        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                        and item.func.attr == "create")
    assert [node.line_number for node in nodes] == call_lines
    assert first.function_name is None
    assert first.column_number == 8
    assert first.current_model == "fixture/model-one"
    assert first.model.kind == "literal"
    assert first.messages.kind == "reference"
    assert first.messages.reference == "messages"
    assert first.call_signature == "openai.OpenAI.chat.completions.create(...)"
    assert first.response_format.value == {"type": "json_object"}
    assert nested.function_name == "outer.inner"
    assert nested.current_model is None
    assert nested.model.kind == "reference"
    assert nested.model.reference == "MODEL"
    assert nested.messages.kind == "unresolved"
    assert "SYSTEM_PROMPT" in nested.messages.references
    assert "query" in nested.messages.references


def test_async_aliases_and_assignments():
    result = scan_repository(str(FIXTURES))
    nodes = [node for node in result.nodes if node.file_path == "supported_async.py"]
    assert [node.function_name for node in nodes] == ["module_alias", "constructor_alias"]
    assert all(node.call_signature == "openai.AsyncOpenAI.chat.completions.create(...)" for node in nodes)
    assert nodes[0].current_model == "fixture/async-model"
    assert nodes[1].current_model is None
    assert nodes[1].model.reference == "configuration.model"


@pytest.mark.parametrize("imports,assignment", [
    ("from openai import OpenAI", "client = OpenAI()"),
    ("from openai import OpenAI as Client", "client = Client()"),
    ("from openai import AsyncOpenAI as Client", "client = Client()"),
    ("import openai", "client = openai.OpenAI()"),
    ("import openai as oai", "client = oai.AsyncOpenAI()"),
    ("from openai import OpenAI", "Constructor = OpenAI\nclient: object = Constructor()"),
    ("from openai import OpenAI", "original = OpenAI()\nclient = original"),
])
def test_recognizable_provenance(tmp_path, imports, assignment):
    source(tmp_path, f"{imports}\n{assignment}\n{CALL}")
    assert len(scan_repository(str(tmp_path)).nodes) == 1


@pytest.mark.parametrize("content", [
    CALL,
    "from other_sdk import OpenAI\nclient = OpenAI()\n" + CALL,
    "from .openai import OpenAI\nclient = OpenAI()\n" + CALL,
    "from openai import OpenAI\nclient = factory(OpenAI)\n" + CALL,
    PREAMBLE + "client = unrelated\n" + CALL,
    PREAMBLE + "def f(client):\n    " + CALL,
    PREAMBLE + "def f():\n    " + CALL + "    client = unrelated\n",
    PREAMBLE + "def f():\n    " + CALL + "client = unrelated\n",
    PREAMBLE + "if condition:\n    client = unrelated\n" + CALL,
    PREAMBLE + "if condition:\n    client = OpenAI()\n    " + CALL,
    PREAMBLE + "client.chat = unrelated\n" + CALL,
    PREAMBLE + "alias = client\nalias.chat = unrelated\n" + CALL,
    PREAMBLE + "alias = client\ndef f():\n    " + CALL + "alias.chat = unrelated\n",
    "import openai as oai\nalias = oai\nalias.OpenAI = unrelated\nclient = oai.OpenAI()\n" + CALL,
    PREAMBLE + "def f():\n    " + CALL + "client.chat = unrelated\n",
    PREAMBLE + "from other import *\n" + CALL,
    PREAMBLE + "def f():\n    " + CALL + "from other import *\n",
    "from openai import OpenAI\nclass Example:\n    client = OpenAI()\n    def f(self):\n        " + CALL,
    "from openai import OpenAI\nclass Example:\n    def f(self):\n        self.client = OpenAI()\n        self.client.chat.completions.create()\n",
    PREAMBLE + "def mutate():\n    global client\n    client = other\n" + CALL,
    PREAMBLE + "def f():\n    global client\n    " + CALL,
    "from openai import OpenAI\nif condition:\n    client = OpenAI()\n" + CALL,
    "from openai import OpenAI\nclient = OpenAI()\nclient.responses.create(model='other-method')\n",
    "import openai as oai\noai.chat.completions.create(model='module-level-sdk-shortcut')\n",
    PREAMBLE + "[client.chat.completions.create() for client in unknown]\n",
    PREAMBLE + "lambda client: client.chat.completions.create()\n",
])
def test_unproven_shadowed_mutated_and_unsupported_clients(tmp_path, content):
    source(tmp_path, content)
    result = scan_repository(str(tmp_path))
    assert result.complete
    assert not result.nodes


def test_known_client_inside_branches_and_nested_local_scopes(tmp_path):
    source(tmp_path, PREAMBLE + """
if flag:
    client.chat.completions.create(model="branch")
def outer():
    local = OpenAI()
    def inner():
        return local.chat.completions.create(model="nested")
    return inner()
""")
    nodes = scan_repository(str(tmp_path)).nodes
    assert [node.current_model for node in nodes] == ["branch", "nested"]
    assert nodes[1].function_name == "outer.inner"


@pytest.mark.parametrize("shadow", ["openai.py", "openai/__init__.py", "agent/openai.py"])
def test_local_openai_modules_make_sdk_provenance_ambiguous(tmp_path, shadow):
    source(tmp_path, "raise RuntimeError('LOCAL MODULE MUST NEVER BE IMPORTED')\n", shadow)
    source(tmp_path, PREAMBLE + CALL, "agent/app.py")
    result = scan_repository(str(tmp_path))
    assert not result.nodes
    assert codes(result) == {"sdk_import_ambiguous"}
    assert not result.complete


@pytest.mark.parametrize("expression,kind,reference", [
    ('"literal-model"', "literal", None),
    ("MODEL", "reference", "MODEL"),
    ("settings.model", "reference", "settings.model"),
    ("get_model()", "unresolved", None),
    ('f"model-{suffix}"', "unresolved", None),
    ("None", "unresolved", None),
    ("42", "unresolved", None),
])
def test_literal_and_dynamic_models(tmp_path, expression, kind, reference):
    source(tmp_path, PREAMBLE + f"client.chat.completions.create(model={expression})\n")
    node = scan_repository(str(tmp_path)).nodes[0]
    assert node.model.kind == kind
    assert node.model.reference == reference
    assert node.current_model == ("literal-model" if kind == "literal" else None)


def test_metadata_redacts_prompt_source_and_arbitrary_schema_values(tmp_path):
    private = "PRIVATE_LITERAL_MUST_NOT_LEAK"
    source(tmp_path, PREAMBLE + f'''
client.chat.completions.create(
    model="fixture/model",
    messages=[{{"role": "user", "content": "{private}"}}],
    response_format={{
        "type": "json_schema", "api_key": "{private}",
        "json_schema": {{"name": "{private}", "strict": True, "schema": {{
            "type": "object", "description": "{private}",
            "properties": {{"answer": {{"type": "string", "default": "{private}"}}}},
            "required": ["answer"],
        }}}},
    }},
)
''')
    result = scan_repository(str(tmp_path))
    node = result.nodes[0]
    assert node.messages.kind == "literal"
    assert node.messages.value is None
    assert node.response_format.value == {
        "type": "json_schema", "strict": True,
        "schema": {"kind": "literal", "type": "object", "property_count": 1, "required_count": 1},
    }
    serialized = result.to_dict()
    assert json.loads(json.dumps(serialized)) == serialized
    text = json.dumps(serialized, sort_keys=True)
    assert private not in text
    assert "snippet" not in serialized["nodes"][0]
    assert "graph_edges" not in serialized


def test_schema_references_and_dynamic_keyword_unpacking(tmp_path):
    source(tmp_path, PREAMBLE + '''
client.chat.completions.create(response_format={
    "type": "json_schema", "json_schema": {"schema": OUTPUT_SCHEMA}
})
client.chat.completions.create(**kwargs)
client.chat.completions.create(response_format=FORMAT)
client.chat.completions.create(response_format={"type": "json_object", **unknown})
''')
    nodes = scan_repository(str(tmp_path)).nodes
    assert nodes[0].response_format.value == {
        "type": "json_schema", "schema": {"kind": "reference", "reference": "OUTPUT_SCHEMA"},
    }
    assert "OUTPUT_SCHEMA" in nodes[0].response_format.references
    assert nodes[0].model.kind == "missing"
    assert nodes[1].model.kind == nodes[1].messages.kind == nodes[1].response_format.kind == "unresolved"
    assert nodes[2].response_format.reference == "FORMAT"
    assert nodes[3].response_format.value is None


def test_unresolved_schema_definition_is_not_reported_as_missing(tmp_path):
    source(tmp_path, PREAMBLE + '''
client.chat.completions.create(response_format={
    "type": "json_schema", "json_schema": DEFINITION
})
client.chat.completions.create(response_format={
    "type": "json_schema", "json_schema": {**dynamic_definition}
})
''')
    nodes = scan_repository(str(tmp_path)).nodes
    assert nodes[0].response_format.value == {
        "type": "json_schema",
        "schema": {"kind": "unresolved", "definition_reference": "DEFINITION"},
    }
    assert nodes[1].response_format.value == {
        "type": "json_schema", "schema": {"kind": "unresolved"},
    }


def test_syntax_error_is_controlled_and_does_not_leak_source(tmp_path):
    source(tmp_path, 'private = "DO_NOT_ECHO_SYNTAX_SECRET"\nif (\n', "broken.py")
    source(tmp_path, PREAMBLE + CALL, "valid.py")
    result = scan_repository(str(tmp_path))
    assert not result.complete
    assert result.scanned_files_count == 1
    assert len(result.nodes) == 1
    assert codes(result) == {"syntax_error"}
    assert result.diagnostics[0].file_path == "broken.py"
    assert result.diagnostics[0].line_number == 2
    assert "DO_NOT_ECHO_SYNTAX_SECRET" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("raw", [
    b"# coding: utf-8\nvalue = '\xff'\n",
    b"# coding: nonexistent_codec\npass\n",
    b"\xef\xbb\xbf# coding: latin-1\npass\n",
    b"# coding: unicode_escape\nvalue = '\\ud800'\n",
])
def test_invalid_source_encodings(tmp_path, raw):
    (tmp_path / "invalid.py").write_bytes(raw)
    result = scan_repository(str(tmp_path))
    assert codes(result) == {"encoding_error"}
    assert result.scanned_files_count == 0
    assert result.total_source_bytes_read == len(raw)


def test_source_encoding_cookie_and_utf8_bom(tmp_path):
    latin = "# coding: latin-1\n# caf\xe9\n" + PREAMBLE + CALL
    (tmp_path / "latin.py").write_bytes(latin.encode("latin-1"))
    (tmp_path / "bom.py").write_bytes((PREAMBLE + CALL).encode("utf-8-sig"))
    result = scan_repository(str(tmp_path))
    assert result.complete
    assert len(result.nodes) == result.scanned_files_count == 2


def test_binary_disguised_as_python_is_not_parsed(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02")
    result = scan_repository(str(tmp_path))
    assert result.scanned_files_count == 0
    assert codes(result) == {"binary_source"}


def test_source_grammar_remains_python_311_on_newer_hosts(tmp_path):
    source(tmp_path, "def generic[T](value: T):\n    return value\n")
    result = scan_repository(str(tmp_path))
    assert result.scanned_files_count == 0
    assert codes(result) == {"syntax_error"}


@pytest.mark.parametrize("failure", [PermissionError, FileNotFoundError])
def test_unreadable_or_disappearing_file_is_controlled(tmp_path, monkeypatch, failure):
    bad = source(tmp_path, PREAMBLE + CALL, "bad.py")
    source(tmp_path, PREAMBLE + CALL, "valid.py")
    original = os.open

    def unavailable(path, flags, *args, **kwargs):
        if Path(path).name == bad.name and not flags & getattr(os, "O_DIRECTORY", 0):
            raise failure("PRIVATE_OS_ERROR_MUST_NOT_LEAK")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", unavailable)
    result = scan_repository(str(tmp_path))
    assert codes(result) == {"read_error"}
    assert result.scanned_files_count == len(result.nodes) == 1
    assert "PRIVATE_OS_ERROR" not in json.dumps(result.to_dict())


def test_unreadable_directory_is_controlled(tmp_path, monkeypatch):
    (tmp_path / "blocked").mkdir()
    blocked = (tmp_path / "blocked").stat()
    source(tmp_path, PREAMBLE + CALL)
    original = os.scandir

    def unavailable(path):
        info = os.fstat(path) if isinstance(path, int) else None
        is_blocked = (
            (info.st_dev, info.st_ino) == (blocked.st_dev, blocked.st_ino)
            if info is not None else Path(path).name == "blocked"
        )
        if is_blocked:
            raise PermissionError("private error")
        return original(path)

    monkeypatch.setattr(os, "scandir", unavailable)
    result = scan_repository(str(tmp_path))
    assert len(result.nodes) == 1
    assert codes(result) == {"directory_error"}


def test_per_file_byte_limit_and_exact_boundary(tmp_path):
    raw = (PREAMBLE + CALL).encode()
    (tmp_path / "fits.py").write_bytes(raw)
    (tmp_path / "too_large.py").write_bytes(raw + b"#")
    result = scan_repository(str(tmp_path), options=ScannerOptions(max_file_bytes=len(raw)))
    assert len(result.nodes) == 1
    assert result.total_source_bytes_read == len(raw)
    assert codes(result) == {"file_size_limit"}
    assert result.diagnostics[0].file_path == "too_large.py"


def test_aggregate_limit_counts_invalid_files_and_never_overreads(tmp_path):
    invalid = b"if (\n"
    (tmp_path / "a_invalid.py").write_bytes(invalid)
    raw = (PREAMBLE + CALL).encode()
    (tmp_path / "b_valid.py").write_bytes(raw)
    (tmp_path / "c_skipped.py").write_bytes(raw)
    budget = len(invalid) + len(raw)
    result = scan_repository(str(tmp_path), options=ScannerOptions(max_total_bytes=budget))
    assert result.total_source_bytes_read == budget
    assert result.discovered_files_count == 3
    assert result.scanned_files_count == len(result.nodes) == 1
    assert codes(result) == {"syntax_error", "total_bytes_limit"}


def test_file_discovery_limit_is_deterministic(tmp_path):
    for name in ["z.py", "b.py", "a.py"]:
        source(tmp_path, PREAMBLE + CALL, name)
    options = ScannerOptions(max_files=2)
    result = scan_repository(str(tmp_path), options=options)
    assert result.discovered_files_count == result.scanned_files_count == 2
    assert [node.file_path for node in result.nodes] == ["a.py", "b.py"]
    assert codes(result) == {"file_count_limit"}
    assert not result.complete
    assert result.to_dict() == scan_repository(str(tmp_path), options=options).to_dict()


def test_directory_entry_and_ast_limits_report_incomplete_coverage(tmp_path):
    source(tmp_path, PREAMBLE + CALL)
    source(tmp_path, "pass\n", "other.py")
    limited = scan_repository(str(tmp_path), options=ScannerOptions(max_directory_entries=1))
    assert not limited.nodes
    assert codes(limited) == {"directory_entry_limit"}
    limited_ast = scan_repository(str(tmp_path), options=ScannerOptions(max_ast_nodes=1))
    assert not limited_ast.nodes
    assert codes(limited_ast) == {"ast_node_limit"}


def test_metadata_budget_preserves_explicit_uncertainty(tmp_path):
    source(tmp_path, PREAMBLE + 'client.chat.completions.create(messages=["a", "b", "c"])\n')
    result = scan_repository(str(tmp_path), options=ScannerOptions(max_metadata_nodes=2))
    assert result.nodes[0].messages.kind == "unresolved"
    assert result.nodes[0].messages.value is None


@pytest.mark.parametrize("directory", [".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"])
def test_excluded_directories_are_not_read(tmp_path, monkeypatch, directory):
    source(tmp_path, PREAMBLE + CALL, f"{directory}/hidden.py")
    source(tmp_path, PREAMBLE + CALL)
    original = os.open

    def guarded(path, flags, *args, **kwargs):
        inspected = Path(path)
        if not inspected.is_absolute():
            inspected = tmp_path / inspected
        assert directory not in inspected.relative_to(tmp_path).parts
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    result = scan_repository(str(tmp_path))
    assert result.complete
    assert result.discovered_files_count == len(result.nodes) == 1


def test_non_python_files_and_environment_contents_are_not_read(tmp_path, monkeypatch):
    for name in [".env", ".env.example", "notebook.ipynb", "archive.zip", "app.pyc", "bundle.js"]:
        source(tmp_path, "PRIVATE_NON_PYTHON_CONTENT", name)
    source(tmp_path, PREAMBLE + CALL)
    original = os.open

    def guarded(path, flags, *args, **kwargs):
        assert flags & getattr(os, "O_DIRECTORY", 0) or Path(path).suffix == ".py"
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    result = scan_repository(str(tmp_path))
    assert result.complete
    assert result.discovered_files_count == 1


def make_link(link: Path, target: Path, directory: bool = False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Symbolic links unavailable on this platform (errno {getattr(error, 'errno', None)}).")


@pytest.mark.parametrize("directory", [False, True])
def test_links_outside_root_are_skipped_before_reading(tmp_path, monkeypatch, directory):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = source(outside, PREAMBLE + CALL)
    make_link(root / ("linked" if directory else "linked.py"), outside if directory else target, directory)
    original = os.open

    def guarded(path, flags, *args, **kwargs):
        assert Path(path).is_relative_to(root)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    result = scan_repository(str(root))
    assert not result.nodes
    assert result.total_source_bytes_read == 0
    assert codes(result) == {"link_skipped"}


def test_resolved_path_outside_root_is_rejected_before_open(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    candidate = source(root, PREAMBLE + CALL)
    outside = source(tmp_path, PREAMBLE + CALL, "outside.py")
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == candidate:
            return outside
        return original(path, *args, **kwargs)

    original_open = os.open

    def forbidden_open(path, flags, *args, **kwargs):
        if flags & getattr(os, "O_DIRECTORY", 0):
            return original_open(path, flags, *args, **kwargs)
        pytest.fail("An outside-root candidate must never be opened.")

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(os, "open", forbidden_open)
    result = scan_repository(str(root))
    assert not result.nodes
    assert result.total_source_bytes_read == 0
    assert codes(result) == {"outside_root"}


def test_file_replaced_between_inspection_and_open_is_not_read(tmp_path, monkeypatch):
    candidate = source(tmp_path, PREAMBLE + CALL)
    replacement = source(tmp_path, "PRIVATE_REPLACEMENT_CONTENT", "replacement.txt")
    original = os.open

    def replaced(path, flags, *args, **kwargs):
        if Path(path).name == candidate.name and not flags & getattr(os, "O_DIRECTORY", 0):
            return original(replacement, flags, *args, **kwargs)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replaced)
    result = scan_repository(str(tmp_path))
    assert not result.nodes
    assert result.total_source_bytes_read == 0
    assert codes(result) == {"file_changed"}


def test_link_as_selected_root_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    source(target, PREAMBLE + CALL)
    link = tmp_path / "link"
    make_link(link, target, True)
    result = scan_repository(str(link))
    assert not result.nodes
    assert codes(result) == {"link_skipped"}


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions require Windows.")
@pytest.mark.parametrize("selected_root", [False, True])
def test_windows_directory_junctions_are_skipped(tmp_path, monkeypatch, selected_root):
    import _winapi

    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    source(outside, PREAMBLE + CALL)
    junction = root / "junction"
    try:
        _winapi.CreateJunction(str(outside), str(junction))
    except OSError as error:
        pytest.skip(f"Directory junction creation unavailable (errno {error.errno}).")
    original = os.scandir

    def guarded(path):
        assert Path(path) == root
        return original(path)

    monkeypatch.setattr(os, "scandir", guarded)
    try:
        result = scan_repository(str(junction if selected_root else root))
        assert result.total_source_bytes_read == 0
        assert not result.nodes
        assert codes(result) == {"link_skipped"}
    finally:
        junction.rmdir()


def test_missing_and_non_directory_roots_are_diagnostics(tmp_path):
    assert codes(scan_repository(str(tmp_path / "missing"))) == {"root_error"}
    path = source(tmp_path, "pass\n")
    assert codes(scan_repository(str(path))) == {"invalid_root"}


def test_deterministic_order_ids_and_serialization_across_root_locations(tmp_path):
    for folder in ["first", "second"]:
        source(tmp_path / folder, PREAMBLE + CALL + CALL, "nested/z.py")
        source(tmp_path / folder, PREAMBLE + CALL, "a.py")
    first = scan_repository(str(tmp_path / "first"))
    repeated = scan_repository(str(tmp_path / "first"))
    relocated = scan_repository(str(tmp_path / "second"))
    assert first.to_dict() == repeated.to_dict()
    assert [node.node_id for node in first.nodes] == [node.node_id for node in relocated.nodes]
    assert len({node.node_id for node in first.nodes}) == 3
    assert [node.file_path for node in first.nodes] == ["a.py", "nested/z.py", "nested/z.py"]
    assert first.nodes[1].line_number < first.nodes[2].line_number
    assert all("\\" not in node.file_path for node in first.nodes)


def test_scanning_never_executes_import_time_side_effects(tmp_path):
    marker = tmp_path / "executed.marker"
    source(tmp_path, f'''
from pathlib import Path
Path({str(marker)!r}).write_text("THIS MUST NEVER RUN")
raise RuntimeError("This module must never be imported")
''' + PREAMBLE + CALL)
    result = scan_repository(str(tmp_path))
    assert result.complete
    assert len(result.nodes) == 1
    assert not marker.exists()


@pytest.mark.parametrize("field", [
    "max_files", "max_file_bytes", "max_total_bytes", "max_directory_entries",
    "max_directory_depth", "max_ast_nodes", "max_metadata_nodes",
])
@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_limits_fail_explicitly(field, value):
    with pytest.raises(ValueError, match=field):
        ScannerOptions(**{field: value})


def test_starred_assignment_invalidates_client_provenance(tmp_path):
    source(tmp_path, PREAMBLE + "*client, = [unrelated]\n" + CALL)
    assert not scan_repository(str(tmp_path)).nodes


@pytest.mark.parametrize("statement", [
    "items[(client := unrelated)] = 0",
    "items[(client := unrelated)]: object = 0",
    "items[(client := unrelated)] += 1",
    "del items[(client := unrelated)]",
])
def test_assignment_target_expressions_invalidate_provenance(tmp_path, statement):
    source(tmp_path, PREAMBLE + statement + "\n" + CALL)
    assert not scan_repository(str(tmp_path)).nodes


def test_supported_call_in_assignment_target_is_discovered(tmp_path):
    source(tmp_path, PREAMBLE + 'items[client.chat.completions.create(model="fixture/model")] = 0\n')
    nodes = scan_repository(str(tmp_path)).nodes
    assert len(nodes) == 1
    assert nodes[0].current_model == "fixture/model"


@pytest.mark.parametrize("literal", [
    "sk-FAKE_AUDIT_CREDENTIAL_DO_NOT_EXPORT",
    "github_pat_FAKE_AUDIT_CREDENTIAL_DO_NOT_EXPORT",
    "Bearer FAKE_AUDIT_CREDENTIAL_DO_NOT_EXPORT",
    "PRIVATE PROMPT ACCIDENTALLY USED AS A MODEL",
    "oversized-model-" + "x" * 1024,
])
def test_credential_like_or_arbitrary_model_literals_are_redacted(tmp_path, literal):
    source(tmp_path, PREAMBLE + f"client.chat.completions.create(model={literal!r})\n")
    result = scan_repository(str(tmp_path))
    assert result.nodes[0].current_model is None
    assert result.nodes[0].model.kind == "unresolved"
    assert literal not in json.dumps(result.to_dict())


@pytest.mark.skipif(os.name != "nt", reason="The regression requires Windows junctions.")
def test_junction_swaps_cannot_substitute_an_outside_file(tmp_path, monkeypatch):
    import _winapi

    root = tmp_path / "repo"
    inside = root / "package"
    holding = root / "holding"
    outside = tmp_path / "outside"
    source(inside, "pass\n")
    source(outside, PREAMBLE + CALL)
    candidate = inside / "app.py"
    # Every rename/removal below concerns these newly created temporary paths.
    assert all(path.is_absolute() and path.is_relative_to(tmp_path)
               for path in (inside, holding, outside))

    def substitute():
        inside.rename(holding)
        try:
            _winapi.CreateJunction(str(outside), str(inside))
        except OSError:
            holding.rename(inside)
            raise

    def restore():
        inside.rmdir()  # Remove the junction itself, never its target.
        holding.rename(inside)

    try:
        substitute()
    except OSError as error:
        pytest.skip(f"Junction creation unavailable (errno {error.errno}).")
    restore()
    original_lstat, original_open = Path.lstat, os.open
    swapped_stat = False

    def lstat_during_swap(path, *args, **kwargs):
        nonlocal swapped_stat
        if path == candidate and not swapped_stat:
            swapped_stat = True
            substitute()
            try:
                return original_lstat(path, *args, **kwargs)
            finally:
                restore()
        return original_lstat(path, *args, **kwargs)

    def open_during_swap(path, flags, *args, **kwargs):
        if Path(path) == candidate:
            substitute()
            try:
                return original_open(path, flags, *args, **kwargs)
            finally:
                restore()
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat_during_swap)
    monkeypatch.setattr(os, "open", open_during_swap)
    result = scan_repository(str(root))
    assert swapped_stat
    assert not result.nodes
    assert result.total_source_bytes_read == 0
    assert not result.complete


@pytest.mark.skipif(os.name != "nt", reason="The regression covers Windows path syntax.")
@pytest.mark.parametrize("outside", [r"Z:\outside\app.py", r"\\audit-invalid\share\app.py"])
def test_other_drives_and_unc_candidates_are_rejected_without_access(tmp_path, monkeypatch, outside):
    candidate = source(tmp_path, PREAMBLE + CALL)
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == candidate:
            return Path(outside)
        return original(path, *args, **kwargs)

    def forbidden_open(*args, **kwargs):
        pytest.fail("No outside-drive or UNC source may be opened.")

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(os, "open", forbidden_open)
    result = scan_repository(str(tmp_path))
    assert codes(result) == {"outside_root"}
    assert result.total_source_bytes_read == 0


@pytest.mark.skipif(os.name != "nt", reason="Extended drive paths require Windows.")
def test_extended_windows_root_preserves_relative_paths(tmp_path):
    source(tmp_path, PREAMBLE + CALL)
    result = scan_repository("\\\\?\\" + str(tmp_path))
    assert result.complete
    assert len(result.nodes) == 1
    assert result.nodes[0].file_path == "app.py"


@pytest.mark.skipif(os.name != "nt", reason="The regression verifies Windows opened handles.")
def test_outside_handle_is_rejected_even_if_path_and_stat_are_restored(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    candidate = source(root, "pass\n")
    outside = source(tmp_path, PREAMBLE + CALL, "outside.py")
    outside_info = outside.stat()
    original_lstat, original_open = Path.lstat, os.open

    def substituted_stat(path, *args, **kwargs):
        if path == candidate:
            return outside_info
        return original_lstat(path, *args, **kwargs)

    def substituted_open(path, flags, *args, **kwargs):
        return original_open(outside if Path(path) == candidate else path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", substituted_stat)
    monkeypatch.setattr(os, "open", substituted_open)
    result = scan_repository(str(root))
    assert not result.nodes
    assert result.total_source_bytes_read == 0
    assert codes(result) == {"file_changed"}


def test_inline_schema_obeys_metadata_budget(tmp_path):
    source(tmp_path, PREAMBLE + '''
client.chat.completions.create(response_format={
    "type": "json_schema", "json_schema": {"schema": {
        "type": "object", "properties": {"answer": {"type": "string"}}
    }}
})
''')
    result = scan_repository(str(tmp_path), options=ScannerOptions(max_metadata_nodes=2))
    assert result.nodes[0].response_format.kind == "unresolved"
    assert result.nodes[0].response_format.value is None
    assert codes(result) == {"metadata_limit"}
    assert not result.complete


def test_source_changes_during_read_are_diagnosed(tmp_path, monkeypatch):
    candidate = source(tmp_path, PREAMBLE + CALL)
    initial = candidate.stat()
    original = os.fdopen

    class ChangedDuringRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            raw = self.stream.read(size)
            candidate.write_bytes(b"#" + b" " * (initial.st_size - 1))
            os.utime(candidate, ns=(initial.st_atime_ns, initial.st_mtime_ns + 2_000_000_000))
            return raw

    def changed_stream(*args, **kwargs):
        return ChangedDuringRead(original(*args, **kwargs))

    monkeypatch.setattr(os, "fdopen", changed_stream)
    result = scan_repository(str(tmp_path))
    assert not result.nodes
    assert result.total_source_bytes_read == initial.st_size
    assert codes(result) == {"file_changed"}


def test_utf8_columns_and_same_line_call_ids_are_distinct(tmp_path):
    call = 'client.chat.completions.create(model="fixture/model")'
    prefix = "\u03c0 = 0; "
    source(tmp_path, PREAMBLE + prefix + call + "; " + call + "\n")
    first, second = scan_repository(str(tmp_path)).nodes
    assert first.column_number == len(prefix.encode("utf-8"))
    assert second.column_number == len((prefix + call + "; ").encode("utf-8"))
    assert first.node_id != second.node_id


def test_directory_depth_limit_bounds_ancestor_work_and_reports_skips(tmp_path):
    source(tmp_path, PREAMBLE + CALL, "one/two/allowed.py")
    source(tmp_path, PREAMBLE + CALL, "one/two/three/blocked.py")
    result = scan_repository(str(tmp_path), options=ScannerOptions(max_directory_depth=2))
    assert [node.file_path for node in result.nodes] == ["one/two/allowed.py"]
    assert result.discovered_files_count == result.scanned_files_count == 1
    assert codes(result) == {"directory_depth_limit"}
    assert result.diagnostics[0].file_path == "one/two/three"
    assert not result.complete


# Phase 2 graph tests stay in this explicitly owned compiler test file.
def flow_call(model: str, messages: str = "[]") -> str:
    return f"client.chat.completions.create(model={model!r}, messages={messages})"


def scan_graph(tmp_path: Path, body: str, *, options: GraphOptions | None = None):
    source(tmp_path, PREAMBLE + body)
    scan = scan_repository(str(tmp_path))
    return scan, build_workflow_graph(str(tmp_path), scan, options)


def edge_models(scan, graph):
    models = {node.node_id: node.current_model for node in scan.nodes}
    return {(models[edge.from_node_id], models[edge.to_node_id]) for edge in graph.edges}


def test_graph_scanner_fingerprints_preserve_ids_and_serialization(tmp_path):
    path = source(tmp_path, PREAMBLE + CALL)
    first = scan_repository(str(tmp_path))
    second = scan_repository(str(tmp_path))
    assert first.to_dict() == second.to_dict()
    assert len(first.source_fingerprints) == 1
    assert first.source_fingerprints[0].file_path == "app.py"
    assert len(first.source_fingerprints[0].sha256) == 64
    assert first.source_options == ScannerOptions()
    path.write_text(PREAMBLE + CALL.replace("fixture/model", "fixture/other"), encoding="utf-8")
    changed = scan_repository(str(tmp_path))
    assert first.nodes[0].node_id == changed.nodes[0].node_id
    assert first.source_fingerprints != changed.source_fingerprints


def test_graph_direct_dependency_has_traceable_evidence(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nsecond = "
        + flow_call("fixture/b", '[{"role": "user", "content": first.choices[0].message.content}]') + "\n")
    assert graph.complete
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}
    assert graph.node_ids == tuple(node.node_id for node in scan.nodes)
    edge = graph.edges[0]
    assert edge.kind == "data_dependency"
    evidence = edge.evidence[0]
    assert evidence.file_path == "app.py"
    assert evidence.argument == "messages"
    assert evidence.reference == "first.choices[].message.content"
    assert evidence.aliases == ("first",)
    assert evidence.line_number == scan.nodes[1].line_number
    assert evidence.column_number > scan.nodes[1].column_number
    payload = graph.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert "graph_edges" not in payload


def test_graph_aliases_and_container_assignments(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias = first\n"
        "messages = [{\"role\": \"user\", \"content\": alias}]\n"
        "second = " + flow_call("fixture/b", "messages") + "\n")
    assert graph.complete
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}
    assert graph.edges[0].evidence[0].aliases == ("first", "alias", "messages")


def test_graph_fan_in_fan_out_and_disconnected_calls(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\n"
        "other = " + flow_call("fixture/c") + "\n"
        "combined = " + flow_call("fixture/b", "[first, other]") + "\n"
        "branch = " + flow_call("fixture/d", "first") + "\n"
        "independent = " + flow_call("fixture/e") + "\n")
    assert graph.complete
    assert edge_models(scan, graph) == {
        ("fixture/a", "fixture/b"), ("fixture/c", "fixture/b"), ("fixture/a", "fixture/d"),
    }


def test_graph_does_not_infer_line_order_shared_models_or_shared_prompts(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "PROMPT = 'PRIVATE_SHARED_PROMPT'\nfirst = " + flow_call("fixture/model", "PROMPT")
        + "\nsecond = " + flow_call("fixture/model", "PROMPT") + "\n")
    assert len(scan.nodes) == 2
    assert graph.complete
    assert not graph.edges
    assert "PRIVATE_SHARED_PROMPT" not in json.dumps(graph.to_dict())


@pytest.mark.parametrize("overwrite", [
    "first = unrelated", "first = None", "del first", "*first, = [unrelated]",
    "items[(first := unrelated)] = 0",
])
def test_graph_reassignment_invalidates_stale_provenance(tmp_path, overwrite):
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                          + "\n" + overwrite + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    assert not graph.edges


def test_graph_rebinding_one_alias_does_not_rebind_another(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias = first\nfirst = unrelated\nsecond = "
        + flow_call("fixture/b", "alias") + "\n")
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}


def test_graph_same_name_in_separate_and_nested_functions_is_isolated(tmp_path):
    body = (
        "def producer():\n    first = " + flow_call("fixture/a") + "\n"
        "def consumer(first):\n    second = " + flow_call("fixture/b", "first") + "\n"
        "def outer():\n    first = " + flow_call("fixture/c") + "\n"
        "    def inner():\n        second = " + flow_call("fixture/d", "first") + "\n"
        "    third = " + flow_call("fixture/e", "first") + "\n"
    )
    scan, graph = scan_graph(tmp_path, body)
    assert edge_models(scan, graph) == {("fixture/c", "fixture/e")}
    assert "cross_scope_dependency" in codes(graph)


def test_graph_direct_and_awaited_assignments_within_functions(tmp_path):
    content = '''from openai import AsyncOpenAI
client = AsyncOpenAI()
async def workflow():
    first = await client.chat.completions.create(model="fixture/a", messages=[])
    alias = first
    second = await client.chat.completions.create(model="fixture/b", messages=[alias])
'''
    source(tmp_path, content)
    scan = scan_repository(str(tmp_path))
    graph = build_workflow_graph(str(tmp_path), scan)
    assert graph.complete
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}


@pytest.mark.parametrize("boundary", [
    "if flag:\n    first = other\n",
    "for item in items:\n    pass\n",
    "while flag:\n    pass\n",
    "try:\n    pass\nexcept Exception:\n    first = other\n",
    "with context:\n    pass\n",
])
def test_graph_control_boundaries_do_not_manufacture_edges(tmp_path, boundary):
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a") + "\n"
                          + boundary + "second = " + flow_call("fixture/b", "first") + "\n")
    assert not graph.edges
    assert not graph.complete
    assert "control_flow_boundary" in codes(graph)


def test_graph_calls_inside_branches_remain_vertices_without_edges(tmp_path):
    scan, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
        + "\nif flag:\n    second = " + flow_call("fixture/b", "first") + "\n")
    assert len(scan.nodes) == len(graph.node_ids) == 2
    assert not graph.edges
    assert "control_flow_boundary" in codes(graph)


@pytest.mark.parametrize("operation", [
    "alias, = [first]", "alias = wrapper(first)", "alias = f'{first}'",
    "alias = first + other", "alias = [value for value in first]",
])
def test_graph_complex_or_dynamic_value_flow_stays_unresolved(tmp_path, operation):
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a") + "\n"
                          + operation + "\nsecond = " + flow_call("fixture/b", "alias") + "\n")
    assert not graph.edges
    assert graph.diagnostics


def test_graph_opaque_call_and_mutations_invalidate_aliases(tmp_path):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias = first\n"
        "opaque()\nsecond = " + flow_call("fixture/b", "alias") + "\n")
    assert not graph.edges
    assert "opaque_call_boundary" in codes(graph)


def test_graph_duplicate_edges_retain_distinct_evidence(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias = first\nsecond = "
        + flow_call("fixture/b", "[first, alias, first]") + "\n")
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}
    assert len(graph.edges) == 1
    assert len(graph.edges[0].evidence) == 3
    assert {item.reference for item in graph.edges[0].evidence} == {"first", "alias"}


def test_graph_deterministic_ids_edges_and_serialization(tmp_path):
    scan, first = scan_graph(tmp_path,
        "a = " + flow_call("fixture/a") + "\nb = " + flow_call("fixture/b", "a")
        + "\nc = " + flow_call("fixture/c", "[a, b]") + "\n")
    second = build_workflow_graph(str(tmp_path), scan)
    assert first.to_dict() == second.to_dict()
    assert set(first.node_ids) == {node.node_id for node in scan.nodes}
    assert all(edge.from_node_id in first.node_ids and edge.to_node_id in first.node_ids for edge in first.edges)


@pytest.mark.parametrize("change", ["location", "id", "missing", "duplicate", "path"])
def test_graph_rejects_missing_mismatched_or_duplicate_scan_nodes(tmp_path, change):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    nodes = list(scan.nodes)
    if change == "location":
        nodes[0] = replace(nodes[0], line_number=nodes[0].line_number + 30)
    elif change == "id":
        nodes[0] = replace(nodes[0], node_id="llm_" + "0" * 24)
    elif change == "missing":
        nodes.pop(0)
    elif change == "duplicate":
        nodes.append(nodes[0])
    else:
        nodes[0] = replace(nodes[0], file_path="../PRIVATE_OUTSIDE.py")
    graph = build_workflow_graph(str(tmp_path), replace(scan, nodes=tuple(nodes)))
    assert not graph.edges
    assert not graph.complete
    assert "PRIVATE_OUTSIDE" not in json.dumps(graph.to_dict())


def test_graph_legacy_scan_without_fingerprints_requires_rescan(tmp_path):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    graph = build_workflow_graph(str(tmp_path), replace(scan, source_fingerprints=()))
    assert not graph.edges
    assert codes(graph) == {"missing_source_fingerprint"}


def test_graph_detects_source_changes_even_when_call_ids_stay_the_same(tmp_path):
    body = "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "first") + "\n"
    scan, graph = scan_graph(tmp_path, body)
    assert graph.edges
    source(tmp_path, PREAMBLE + body.replace("messages=first", "messages=other"))
    assert [node.node_id for node in scan.nodes] == [node.node_id for node in scan_repository(str(tmp_path)).nodes]
    stale = build_workflow_graph(str(tmp_path), scan)
    assert not stale.edges
    assert "source_changed" in codes(stale)


@pytest.mark.parametrize("raw", [b"if (\n", b"# coding: utf-8\nx='\xff'\n", b"\x00binary"])
def test_graph_malformed_or_changed_sources_are_controlled(tmp_path, raw):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    (tmp_path / "app.py").write_bytes(raw)
    graph = build_workflow_graph(str(tmp_path), scan)
    assert not graph.edges
    assert "source_unavailable" in codes(graph)
    assert not graph.complete


def test_graph_preserves_stricter_source_budgets_and_reports_skipped_work(tmp_path):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    limited = build_workflow_graph(str(tmp_path), scan, GraphOptions(source_options=ScannerOptions(max_file_bytes=8)))
    assert not limited.edges
    assert "source_file_size_limit" in codes(limited)
    source(tmp_path, PREAMBLE + CALL, "z.py")
    narrow = scan_repository(str(tmp_path), options=ScannerOptions(max_files=1))
    inherited = build_workflow_graph(str(tmp_path), narrow)
    assert not inherited.complete
    assert "source_file_count_limit" in codes(inherited)


@pytest.mark.parametrize("option,value,diagnostic", [
    ("max_analysis_steps", 1, "flow_analysis_limit"),
    ("max_expression_nodes", 2, "expression_limit"),
    ("max_alias_depth", 1, "alias_limit"),
    ("max_value_provenances", 1, "value_provenance_limit"),
])
def test_graph_analysis_limits_are_explicit_and_controlled(tmp_path, option, value, diagnostic):
    scan, _ = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias = first\n"
        "other = " + flow_call("fixture/c") + "\nsecond = " + flow_call("fixture/b", "[alias, other]") + "\n")
    graph = build_workflow_graph(str(tmp_path), scan, GraphOptions(**{option: value}))
    assert not graph.complete
    assert diagnostic in codes(graph)
    if option == "max_analysis_steps":
        assert not graph.edges


def test_graph_edge_and_evidence_limits_report_partial_coverage(tmp_path):
    scan, _ = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "[first, first]")
        + "\nthird = " + flow_call("fixture/c", "first") + "\n")
    graph = build_workflow_graph(str(tmp_path), scan, GraphOptions(max_edges=1, max_evidence_per_edge=1))
    assert len(graph.edges) == 1
    assert len(graph.edges[0].evidence) == 1
    assert {"edge_limit", "edge_evidence_limit"} <= codes(graph)


def test_graph_does_not_execute_side_effects_or_leak_source(tmp_path):
    marker = tmp_path / "executed.marker"
    private = "PRIVATE_GRAPH_PROMPT_AND_EXCEPTION_TEXT"
    body = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text({private!r})\n"
        f"raise RuntimeError({private!r})\n"
        "first = " + flow_call("fixture/a", repr(private)) + "\n"
        "second = " + flow_call("fixture/b", "first") + "\n"
    )
    scan, graph = scan_graph(tmp_path, body)
    assert len(scan.nodes) == 2
    assert not marker.exists()
    assert private not in json.dumps(graph.to_dict())
    assert not graph.edges  # Statements following an unconditional raise are omitted.


def test_graph_repository_mismatch_rejects_edges(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    body = PREAMBLE + "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "first") + "\n"
    source(first_root, body)
    source(second_root, body)
    scan = scan_repository(str(first_root))
    graph = build_workflow_graph(str(second_root), scan)
    assert not graph.edges
    assert "repository_mismatch" in codes(graph)


@pytest.mark.parametrize("failure", [PermissionError, FileNotFoundError])
def test_graph_unreadable_file_is_diagnostic_not_a_fabricated_edge(tmp_path, monkeypatch, failure):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    original = os.open

    def unreadable(path, flags, *args, **kwargs):
        if Path(path).name == "app.py" and not flags & getattr(os, "O_DIRECTORY", 0):
            raise failure("PRIVATE_GRAPH_IO_EXCEPTION")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", unreadable)
    graph = build_workflow_graph(str(tmp_path), scan)
    assert not graph.edges
    assert "source_read_error" in codes(graph)
    assert "PRIVATE_GRAPH_IO_EXCEPTION" not in json.dumps(graph.to_dict())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression.")
def test_graph_reuses_scanner_junction_boundary(tmp_path):
    import _winapi

    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    source(outside, PREAMBLE + "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    initial = scan_repository(str(root))
    junction = root / "junction"
    try:
        _winapi.CreateJunction(str(outside), str(junction))
    except OSError as error:
        pytest.skip(f"Junction creation unavailable (errno {error.errno}).")
    try:
        graph = build_workflow_graph(str(root), initial)
        assert not graph.edges
        assert not graph.node_ids
        assert "source_link_skipped" in codes(graph)
    finally:
        junction.rmdir()


@pytest.mark.parametrize("messages", [
    '{"content": first, "content": unrelated}',
    '{True: first, 1: unrelated}',
    '{"content": first, dynamic_key: unrelated}',
])
def test_graph_review_ambiguous_dictionary_values_are_not_dependencies(tmp_path, messages):
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                          + "\nsecond = " + flow_call("fixture/b", messages) + "\n")
    assert not graph.edges
    assert not graph.complete


@pytest.mark.parametrize("suffix", [".model_dump()", ".chat.completions.create(messages=[])"])
def test_graph_review_nested_calls_sharing_a_start_are_not_the_same_call(tmp_path, suffix):
    scan, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a") + suffix
                              + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    assert len(scan.nodes) == 2
    assert not graph.edges
    assert "opaque_call_boundary" in codes(graph)


def test_graph_review_constructor_arguments_are_not_create_arguments(tmp_path):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\n"
        "second = OpenAI(api_key=first).chat.completions.create(model='fixture/b', messages=[])\n")
    assert not graph.edges


@pytest.mark.parametrize("boundary", [
    "import helper\n",
    "class Mutation:\n    global first\n    first = unrelated\n",
    "@run_now\ndef mutation():\n    global first\n    first = unrelated\n",
])
def test_graph_review_implicit_side_effect_boundaries_invalidate_producers(tmp_path, boundary):
    source(tmp_path, "raise RuntimeError('HELPER MUST NEVER BE IMPORTED')\n", "helper.py")
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a") + "\n"
                          + boundary + "second = " + flow_call("fixture/b", "first") + "\n")
    assert not graph.edges
    assert graph.diagnostics


@pytest.mark.parametrize("selector", ["settings.prompt", "settings['prompt']"])
def test_graph_review_unknown_selectors_do_not_hide_possible_mutation(tmp_path, selector):
    _, graph = scan_graph(tmp_path, "first = " + flow_call("fixture/a") + "\n"
                          + "other = " + selector + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    assert not graph.edges


def test_graph_review_keyword_unpacking_is_a_barrier(tmp_path):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a")
        + "\nsecond = client.chat.completions.create(model='fixture/b', **{'messages': first})\n")
    assert not graph.edges
    assert "unpacking_boundary" in codes(graph)


def test_graph_rebinding_a_producer_name_preserves_evaluation_order(tmp_path):
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\n"
        "first = " + flow_call("fixture/b", "first") + "\n"
        "third = " + flow_call("fixture/c", "first") + "\n")
    assert graph.complete
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b"), ("fixture/b", "fixture/c")}


def test_graph_source_files_have_independent_flow_state(tmp_path):
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/a") + "\n", "a.py")
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/c")
           + "\nsecond = " + flow_call("fixture/b", "first") + "\n", "b.py")
    scan = scan_repository(str(tmp_path))
    graph = build_workflow_graph(str(tmp_path), scan)
    assert graph.complete
    assert edge_models(scan, graph) == {("fixture/c", "fixture/b")}


def test_graph_nested_direct_results_require_named_evidence(tmp_path):
    _, graph = scan_graph(tmp_path, "second = " + flow_call("fixture/b", flow_call("fixture/a")) + "\n")
    assert len(graph.node_ids) == 2
    assert not graph.edges
    assert "unbound_producer" in codes(graph)


def test_graph_duplicate_fingerprints_and_untrusted_diagnostics_are_sanitized(tmp_path):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    duplicate = replace(scan, source_fingerprints=scan.source_fingerprints * 2)
    rejected = build_workflow_graph(str(tmp_path), duplicate)
    assert not rejected.edges
    assert "invalid_source_fingerprint" in codes(rejected)
    private = "PRIVATE_UNTRUSTED_DIAGNOSTIC_MESSAGE"
    input_with_diagnostic = replace(scan, complete=False, diagnostics=(ScanDiagnostic("unknown", private),))
    partial = build_workflow_graph(str(tmp_path), input_with_diagnostic)
    assert "input_scan_incomplete" in codes(partial)
    assert private not in json.dumps(partial.to_dict())


def test_graph_literal_keys_and_prompts_do_not_leak_into_evidence(tmp_path):
    private = "PRIVATE_GRAPH_PROPERTY_AND_PROMPT"
    scan, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a", repr(private)) + "\n"
        f"alias = first[{private!r}]\nsecond = " + flow_call("fixture/b", "alias") + "\n")
    assert edge_models(scan, graph) == {("fixture/a", "fixture/b")}
    assert private not in json.dumps(graph.to_dict())


def test_graph_preserves_syntax_diagnostic_line_numbers(tmp_path):
    source(tmp_path, "pass\nif (\n")
    scan = scan_repository(str(tmp_path))
    graph = build_workflow_graph(str(tmp_path), scan)
    diagnostic = next(item for item in graph.diagnostics if item.code == "source_syntax_error")
    assert diagnostic.file_path == "app.py"
    assert diagnostic.line_number == 2


@pytest.mark.parametrize("selection", [
    "[first, unrelated][1]",
    "{'keep': first, 'discard': unrelated}['discard']",
    "values[1]",
])
def test_graph_review_container_selection_does_not_propagate_every_element(tmp_path, selection):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nvalues = [first, unrelated]\n"
        "second = " + flow_call("fixture/b", selection) + "\n")
    assert not graph.edges
    assert "container_selection" in codes(graph)


def test_graph_review_unknown_unpacking_can_invalidate_prior_bindings(tmp_path):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\nalias, = iterable\nsecond = "
        + flow_call("fixture/b", "first") + "\n")
    assert not graph.edges
    assert "complex_assignment" in codes(graph)


@pytest.mark.parametrize("suspension", ["suspension", "(pending := suspension)"])
def test_graph_unknown_await_invalidates_producer_bindings(tmp_path, suspension):
    # An arbitrary __await__ implementation can rebind this global. Parse only.
    source(tmp_path, '''from openai import AsyncOpenAI
client = AsyncOpenAI()
async def workflow(suspension):
    global first
    first = await client.chat.completions.create(model="fixture/a", messages=[])
    await ''' + suspension + '''
    second = await client.chat.completions.create(model="fixture/b", messages=first)
''')
    scan = scan_repository(str(tmp_path))
    graph = build_workflow_graph(str(tmp_path), scan)
    assert len(scan.nodes) == 2
    assert not graph.edges
    assert not graph.complete
    assert "opaque_await_boundary" in codes(graph)


@pytest.mark.parametrize("parameter", ["value=first", "*, value=first"])
def test_graph_producer_defaults_report_omitted_cross_scope_flow(tmp_path, parameter):
    _, graph = scan_graph(tmp_path,
        "first = " + flow_call("fixture/a") + "\ndef consumer(" + parameter + "):\n"
        "    second = " + flow_call("fixture/b", "value") + "\n")
    assert not graph.edges
    assert not graph.complete
    assert "default_value_boundary" in codes(graph)


def test_graph_late_expression_failure_rolls_back_only_affected_file(tmp_path):
    body = PREAMBLE + "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "first") + "\n"
    source(tmp_path, body + "oversized = [" + ",".join("0" for _ in range(80)) + "]\n", "a.py")
    source(tmp_path, body, "b.py")
    scan = scan_repository(str(tmp_path))
    assert scan.complete
    initial = build_workflow_graph(str(tmp_path), scan)
    assert len(initial.edges) == 2  # An edge exists before the late failure.
    limited = build_workflow_graph(str(tmp_path), scan, GraphOptions(max_expression_nodes=64))
    paths = {node.node_id: node.file_path for node in scan.nodes}
    assert len(limited.edges) == 1
    assert all(paths[edge.from_node_id] == paths[edge.to_node_id] == "b.py" for edge in limited.edges)
    assert not limited.complete
    diagnostic = next(item for item in limited.diagnostics if item.code == "expression_limit")
    assert diagnostic.file_path == "a.py"


def test_graph_node_budget_exact_boundary_and_diagnostic_cap(tmp_path):
    scan, _ = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
                         + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    exact = build_workflow_graph(str(tmp_path), scan, GraphOptions(max_nodes=2))
    assert exact.complete and len(exact.edges) == 1
    rejected = build_workflow_graph(str(tmp_path), scan, GraphOptions(max_nodes=1))
    assert not rejected.edges and not rejected.complete
    assert codes(rejected) == {"node_limit"}
    _, partial = scan_graph(tmp_path, "first = " + flow_call("fixture/a")
        + "\nopaque()\nsecond = " + flow_call("fixture/b", "first") + "\n",
        options=GraphOptions(max_diagnostics=1))
    assert not partial.edges and not partial.complete
    assert len(partial.diagnostics) == 1
    assert codes(partial) == {"diagnostic_limit"}


# Phase 3 exercises the public orchestrator and real source-only components.
def test_analysis_end_to_end_preserves_results_ids_and_serialization(tmp_path):
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/a")
           + "\nsecond = " + flow_call("fixture/b", "first")
           + "\nthird = " + flow_call("fixture/c", "[first, second]") + "\n")
    result = analyze_repository(str(tmp_path))
    assert isinstance(result, ProvisionalAnalysisResult)
    assert result.complete
    assert result.scan_result.complete and result.workflow_graph.complete
    assert len(result.scan_result.nodes) == 3
    assert result.workflow_graph.node_ids == tuple(node.node_id for node in result.scan_result.nodes)
    assert edge_models(result.scan_result, result.workflow_graph) == {
        ("fixture/a", "fixture/b"), ("fixture/a", "fixture/c"), ("fixture/b", "fixture/c"),
    }
    assert all(edge.evidence for edge in result.workflow_graph.edges)
    payload = result.to_dict()
    assert payload == {
        "scan_result": result.scan_result.to_dict(),
        "workflow_graph": result.workflow_graph.to_dict(),
        "complete": True,
    }
    assert json.loads(json.dumps(payload)) == payload
    assert json.dumps(payload) == json.dumps(analyze_repository(str(tmp_path)).to_dict())


def test_analysis_empty_repository_is_complete(tmp_path):
    result = analyze_repository(str(tmp_path))
    assert result.complete
    assert result.scan_result.scanned_files_count == result.scan_result.discovered_files_count == 0
    assert not result.scan_result.nodes
    assert not result.workflow_graph.node_ids and not result.workflow_graph.edges
    assert not result.scan_result.diagnostics and not result.workflow_graph.diagnostics


@pytest.mark.parametrize("scanner_complete,graph_complete", [
    (True, True), (True, False), (False, True), (False, False),
])
def test_analysis_completeness_requires_both_components(tmp_path, scanner_complete, graph_complete):
    baseline = analyze_repository(str(tmp_path))
    result = ProvisionalAnalysisResult(
        replace(baseline.scan_result, complete=scanner_complete),
        replace(baseline.workflow_graph, complete=graph_complete),
    )
    expected = (scanner_complete, graph_complete) == (True, True)
    assert result.complete is expected
    assert result.to_dict()["complete"] is expected


def test_analysis_partial_scan_keeps_valid_edges_and_separate_diagnostics(tmp_path):
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/a")
           + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    source(tmp_path, "if (\n", "broken.py")
    result = analyze_repository(str(tmp_path))
    assert not result.complete and not result.scan_result.complete
    assert len(result.scan_result.nodes) == 2
    assert edge_models(result.scan_result, result.workflow_graph) == {("fixture/a", "fixture/b")}
    assert codes(result.scan_result) == {"syntax_error"}
    assert codes(result.workflow_graph) == {"input_scan_incomplete", "source_syntax_error"}
    payload = result.to_dict()
    assert payload["scan_result"]["diagnostics"] == result.scan_result.to_dict()["diagnostics"]
    assert payload["workflow_graph"]["diagnostics"] == result.workflow_graph.to_dict()["diagnostics"]
    assert "diagnostics" not in payload


def test_analysis_graph_limit_preserves_scan_and_partial_graph(tmp_path):
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/a")
           + "\nsecond = " + flow_call("fixture/b", "first")
           + "\nthird = " + flow_call("fixture/c", "first") + "\n")
    result = analyze_repository(str(tmp_path), graph_options=GraphOptions(max_edges=1))
    assert result.scan_result.complete and len(result.scan_result.nodes) == 3
    assert not result.complete and not result.workflow_graph.complete
    assert len(result.workflow_graph.edges) == 1
    assert codes(result.workflow_graph) == {"edge_limit"}
    assert all(edge.from_node_id in result.workflow_graph.node_ids
               and edge.to_node_id in result.workflow_graph.node_ids for edge in result.workflow_graph.edges)


@pytest.mark.parametrize("limited_component", ["scanner", "graph"])
def test_analysis_source_options_apply_to_the_correct_component(tmp_path, limited_component):
    source(tmp_path, PREAMBLE + CALL)
    scanner_options = ScannerOptions(max_file_bytes=8) if limited_component == "scanner" else None
    graph_options = GraphOptions(source_options=ScannerOptions(max_file_bytes=8)) if limited_component == "graph" else None
    result = analyze_repository(str(tmp_path), scanner_options=scanner_options, graph_options=graph_options)
    assert not result.complete and not result.workflow_graph.edges
    assert "source_file_size_limit" in codes(result.workflow_graph)
    if limited_component == "scanner":
        assert not result.scan_result.nodes and not result.scan_result.complete
        assert codes(result.scan_result) == {"file_size_limit"}
        assert result.scan_result.source_options is scanner_options
    else:
        assert result.scan_result.complete and len(result.scan_result.nodes) == 1
        assert not result.workflow_graph.complete


@pytest.mark.parametrize("custom_options", [False, True])
def test_analysis_calls_scanner_once_and_passes_exact_result_and_options(tmp_path, monkeypatch, custom_options):
    source(tmp_path, PREAMBLE + "first = " + flow_call("fixture/a")
           + "\nsecond = " + flow_call("fixture/b", "first") + "\n")
    scanner_options = ScannerOptions(max_files=3) if custom_options else None
    graph_options = GraphOptions(max_edges=2) if custom_options else None
    events, scans, graphs, opened_sources = [], [], [], []
    original_open = os.open

    def guarded_open(path, flags, *args, **kwargs):
        if not flags & getattr(os, "O_DIRECTORY", 0):
            opened_sources.append(Path(path).name)
        return original_open(path, flags, *args, **kwargs)

    def scan_spy(path, *, options=None):
        events.append("scan")
        assert path == str(tmp_path) and options is scanner_options
        scanned = scan_repository(path, options=options)
        scans.append(scanned)
        return scanned

    def graph_spy(path, scan_result, options=None):
        events.append("graph")
        assert path == str(tmp_path) and options is graph_options
        assert scan_result is scans[0]
        graph = build_workflow_graph(path, scan_result, options)
        graphs.append(graph)
        return graph

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(dag_builder, "scan_repository", scan_spy)
    monkeypatch.setattr(dag_builder, "build_workflow_graph", graph_spy)
    result = analyze_repository(str(tmp_path), scanner_options=scanner_options, graph_options=graph_options)
    assert events == ["scan", "graph"]
    assert result.scan_result is scans[0] and result.workflow_graph is graphs[0]
    assert result.complete and len(result.workflow_graph.edges) == 1
    # One initial read and the graph builder's mandatory guarded verification.
    assert opened_sources == ["app.py", "app.py"]


@pytest.mark.parametrize("invalid_root,diagnostic", [
    ("missing", "root_error"), ("file", "invalid_root"), ("nul", "root_error"),
])
def test_analysis_invalid_roots_preserve_component_error_semantics(tmp_path, invalid_root, diagnostic):
    if invalid_root == "file":
        path = str(source(tmp_path, "pass\n"))
    else:
        path = str(tmp_path / "missing") + ("\x00" if invalid_root == "nul" else "")
    result = analyze_repository(path)
    assert not result.complete and not result.scan_result.complete and not result.workflow_graph.complete
    assert not result.scan_result.nodes and not result.workflow_graph.edges
    assert codes(result.scan_result) == {diagnostic}
    assert codes(result.workflow_graph) == {"input_scan_incomplete", "source_" + diagnostic}


@pytest.mark.parametrize("failing_component", ["scanner", "graph"])
def test_analysis_unexpected_component_exceptions_propagate(tmp_path, monkeypatch, failing_component):
    failure = RuntimeError("TRUSTED_ORCHESTRATION_TEST_FAILURE")
    events = []

    def scanner(path, *, options=None):
        events.append("scan")
        if failing_component == "scanner":
            raise failure
        return scan_repository(path, options=options)

    def builder(path, scan_result, options=None):
        events.append("graph")
        raise failure

    monkeypatch.setattr(dag_builder, "scan_repository", scanner)
    monkeypatch.setattr(dag_builder, "build_workflow_graph", builder)
    with pytest.raises(RuntimeError) as raised:
        analyze_repository(str(tmp_path))
    assert raised.value is failure
    assert events == (["scan"] if failing_component == "scanner" else ["scan", "graph"])


def test_analysis_retains_source_change_detection_between_components(tmp_path, monkeypatch):
    body = PREAMBLE + "first = " + flow_call("fixture/a") + "\nsecond = " + flow_call("fixture/b", "first") + "\n"
    source(tmp_path, body)

    def changed_source_builder(path, scan_result, options=None):
        source(tmp_path, body.replace("messages=first", "messages=other"))
        return build_workflow_graph(path, scan_result, options)

    monkeypatch.setattr(dag_builder, "build_workflow_graph", changed_source_builder)
    result = analyze_repository(str(tmp_path))
    assert result.scan_result.complete and len(result.scan_result.nodes) == 2
    assert not result.complete and not result.workflow_graph.complete
    assert not result.workflow_graph.edges
    assert codes(result.workflow_graph) == {"source_changed"}


def test_analysis_never_executes_target_code_or_exports_private_literals(tmp_path, monkeypatch):
    marker = tmp_path / "executed.marker"
    private = "PRIVATE_UNIFIED_PROMPT_AND_EXCEPTION"
    credential = "sk-FAKE_UNIFIED_CREDENTIAL_DO_NOT_EXPORT"
    source(tmp_path, f"from pathlib import Path\nPath({str(marker)!r}).write_text({private!r})\n"
           "import helper\n" + PREAMBLE + "first = " + flow_call("fixture/a", repr(private))
           + "\nsecond = " + flow_call("fixture/b", "first")
           + "\nthird = " + flow_call(credential) + f"\nraise RuntimeError({private!r})\n")
    source(tmp_path, f"from pathlib import Path\nPath({str(marker)!r}).write_text({private!r})\n", "helper.py")
    source(tmp_path, private, ".env")  # Synthetic test data, never opened by analysis.
    original_open = os.open

    def source_only_open(path, flags, *args, **kwargs):
        assert flags & getattr(os, "O_DIRECTORY", 0) or Path(path).suffix == ".py"
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", source_only_open)
    result = analyze_repository(str(tmp_path))
    assert not marker.exists()
    assert len(result.scan_result.nodes) == 3
    assert edge_models(result.scan_result, result.workflow_graph) == {("fixture/a", "fixture/b")}
    assert not result.complete
    serialized = json.dumps(result.to_dict())
    assert private not in serialized and credential not in serialized
