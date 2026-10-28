"""Tests import the trusted scanner; scanned applications are source data only."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from backend.compiler.ast_scanner import ScannerOptions, scan_repository


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
