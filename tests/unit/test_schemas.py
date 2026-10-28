"""Public contract tests; target applications are never imported or executed."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas import (
    API_SCHEMA_VERSION, DIAGNOSTIC_MESSAGES, ERROR_MESSAGES, Diagnostic, ErrorResponse,
    LLMNode, LimitedSchemaSummary, ScanRequest, ScanResponse, SchemaShapeSummary, SourceLocation,
)


def node_data(index=1, **changes):
    return {
        "node_id": "llm_" + f"{index:024x}", "file_path": "app.py", "line_number": index,
        "column_number": 0, "current_model": "fixture/model",
        "call_signature": "openai.OpenAI.chat.completions.create(...)",
        "model_resolution": "literal", "prompt_resolution": "missing", "schema_resolution": "missing",
        **changes,
    }


def response_data(**changes):
    first, second = LLMNode(**node_data()), LLMNode(**node_data(2))
    return {
        "analysis_id": "analysis_" + "a" * 32,
        "timestamp": datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
        "repository_path": "approved/repository", "nodes": [first, second],
        "graph_edges": [[first.node_id, second.node_id]],
        "scanned_files_count": 1, "discovered_files_count": 1, "total_source_bytes_read": 200,
        "detected_framework": "OpenAI SDK", "data_source": "live",
        "scan_complete": True, "graph_complete": True, "complete": True,
        "scan_diagnostics": [], "graph_diagnostics": [], **changes,
    }


@pytest.mark.parametrize("path", ["repo", "/approved/repo", r"C:\approved\repo", "../other", "repo with spaces"])
def test_scan_request_validates_syntax_without_authorizing_or_inspecting(path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Request schema validation must not inspect the filesystem.")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    assert ScanRequest(repository_path=path).repository_path == path


@pytest.mark.parametrize("path", [
    None, 42, True, b"repo", [], "", "   ", "a\x00b", "a\nb", "a" * 4097,
    "a\u0085b", "a\u2028b", "a\ud800b",
])
def test_invalid_scan_request_values(path):
    with pytest.raises(ValidationError):
        ScanRequest(repository_path=path)


@pytest.mark.parametrize("extra", ["source", "command", "script", "api_key", "options"])
def test_scan_request_rejects_executable_and_unexpected_fields(extra):
    with pytest.raises(ValidationError):
        ScanRequest(repository_path="repo", **{extra: "PRIVATE_UNEXPECTED_INPUT"})


@pytest.mark.parametrize("kind", ["missing", "unresolved", "literal", "reference"])
def test_model_resolution_states_and_null_serialization(kind):
    data = node_data(model_resolution=kind, current_model="fixture/model" if kind == "literal" else None)
    if kind == "reference":
        data.update(model_reference="settings.model", model_references=["settings", "settings.model"])
    node = LLMNode(**data)
    payload = node.model_dump(mode="json")
    assert payload["model_resolution"] == kind
    assert payload["current_model"] == ("fixture/model" if kind == "literal" else None)
    assert payload["function_name"] is None
    assert payload["limited_schema_summary"] is None
    assert payload["prompt_reference"] is None
    assert not {"expected_schema", "snippet", "docstring", "messages", "value"} & payload.keys()
    assert LLMNode.model_validate_json(node.model_dump_json()) == node


@pytest.mark.parametrize("changes", [
    {"model_resolution": "reference"}, {"model_resolution": "literal", "current_model": None},
    {"model_resolution": "unresolved"}, {"model_reference": "MODEL"},
    {"model_references": ["MODEL"]}, {"prompt_resolution": "reference"},
    {"prompt_resolution": "reference", "prompt_reference": "PROMPT"},
    {"schema_resolution": "missing", "schema_references": ["SCHEMA"]},
    {"model_resolution": "guessed"}, {"model_references": ["MODEL", "MODEL"]},
])
def test_inconsistent_resolution_metadata_is_rejected(changes):
    with pytest.raises(ValidationError):
        LLMNode(**node_data(**changes))


def test_prompt_and_schema_references_preserve_syntax_only():
    node = LLMNode(**node_data(
        prompt_resolution="reference", prompt_reference="messages", prompt_references=["messages"],
        schema_resolution="reference", schema_reference="OUTPUT_FORMAT", schema_references=["OUTPUT_FORMAT"],
    ))
    assert node.prompt_reference == "messages"
    assert node.schema_reference == "OUTPUT_FORMAT"
    assert node.limited_schema_summary is None


@pytest.mark.parametrize("reference", ["x['PRIVATE']", "get_prompt()", "a..b", "a." + "b." * 18 + "c", "a" * 257])
def test_references_cannot_contain_expressions_or_unbounded_text(reference):
    with pytest.raises(ValidationError):
        LLMNode(**node_data(prompt_resolution="unresolved", prompt_references=[reference]))


@pytest.mark.parametrize("path", ["../app.py", "/app.py", r"C:\app.py", r"a\app.py", "a//app.py", "a/./app.py", ".", "app.py\n"])
def test_source_locations_reject_noncanonical_or_outside_paths(path):
    with pytest.raises(ValidationError):
        LLMNode(**node_data(file_path=path))


@pytest.mark.parametrize("changes", [
    {"line_number": 0}, {"line_number": -1}, {"line_number": True}, {"line_number": "1"},
    {"column_number": -1}, {"column_number": 1.0}, {"node_id": "node_mock"},
    {"node_id": "llm_" + "a" * 24 + "\n"}, {"call_signature": "arbitrary(source)"},
    {"current_model": "sk-FAKE_DO_NOT_EXPORT"}, {"current_model": "PRIVATE PROMPT TEXT"},
    {"current_model": 42}, {"expected_schema": {"type": "object"}},
    {"snippet": "PRIVATE_SOURCE"}, {"docstring": "PRIVATE_SOURCE"},
])
def test_invalid_locations_models_and_source_exports(changes):
    with pytest.raises(ValidationError):
        LLMNode(**node_data(**changes))


def test_limited_schema_summary_is_typed_and_never_an_expected_schema():
    summary = LimitedSchemaSummary(
        format_type="json_schema", strict=True,
        schema_shape=SchemaShapeSummary(kind="literal", type="object", property_count=2, required_count=1),
    )
    node = LLMNode(**node_data(schema_resolution="literal", limited_schema_summary=summary))
    payload = node.model_dump(mode="json")
    assert payload["limited_schema_summary"]["schema_shape"]["property_count"] == 2
    assert "expected_schema" not in payload
    with pytest.raises(ValidationError):
        SchemaShapeSummary(kind="literal", properties={"PRIVATE": "PRIVATE"})
    with pytest.raises(ValidationError):
        LimitedSchemaSummary(format_type="json_schema", description="PRIVATE_SOURCE")


@pytest.mark.parametrize("shape", [
    {"kind": "missing", "property_count": 1},
    {"kind": "reference"},
    {"kind": "reference", "reference": "SCHEMA", "type": "object"},
    {"kind": "literal", "definition_reference": "DEFINITION"},
    {"kind": "literal", "property_count": True},
    {"kind": "literal", "required_count": -1},
])
def test_schema_summary_rejects_inconsistent_or_coerced_values(shape):
    with pytest.raises(ValidationError):
        SchemaShapeSummary(**shape)


def test_unresolved_schema_definition_remains_distinguishable():
    shape = SchemaShapeSummary(kind="unresolved", definition_reference="DEFINITION")
    summary = LimitedSchemaSummary(format_type="json_schema", schema_shape=shape)
    node = LLMNode(**node_data(schema_resolution="unresolved", schema_references=["DEFINITION"], limited_schema_summary=summary))
    assert node.limited_schema_summary.schema_shape.kind == "unresolved"
    with pytest.raises(ValidationError):
        LimitedSchemaSummary(format_type="json_object", strict=True)


def test_valid_response_preserves_edges_order_ids_and_deterministic_json():
    response = ScanResponse(**response_data())
    payload = response.model_dump(mode="json")
    assert payload["schema_version"] == API_SCHEMA_VERSION
    assert payload["graph_edges"] == [[node_data()["node_id"], node_data(2)["node_id"]]]
    assert payload["timestamp"] == "2026-10-28T12:00:00.000000Z"
    assert ScanResponse.model_validate_json(response.model_dump_json()) == response
    assert ScanResponse.model_validate(payload) == response
    assert response.model_dump_json() == ScanResponse(**response_data()).model_dump_json()
    assert not {"source_fingerprints", "verified_sources", "evidence", "source_options"} & payload.keys()


@pytest.mark.parametrize("changes", [
    {"graph_edges": [[node_data()["node_id"], "llm_" + "f" * 24]]},
    {"graph_edges": [[node_data()["node_id"], node_data()["node_id"]]]},
    {"graph_edges": [[node_data()["node_id"]]]},
    {"graph_edges": ["ab"]},
    {"graph_edges": [[node_data()["node_id"], node_data(2)["node_id"]]] * 2},
    {"nodes": [LLMNode(**node_data()), LLMNode(**node_data())]},
    {"scanned_files_count": 2}, {"scanned_files_count": 0},
    {"discovered_files_count": -1}, {"total_source_bytes_read": True},
    {"total_source_bytes_read": "200"}, {"scanned_files_count": 1.0},
    {"data_source": "fallback"}, {"detected_framework": "Python Agent"},
    {"schema_version": "unreviewed.v2"}, {"analysis_id": "arbitrary"},
    {"source_fingerprints": []}, {"graph_evidence": []},
])
def test_response_rejects_invalid_endpoints_counts_and_fabricated_extensions(changes):
    with pytest.raises(ValidationError):
        ScanResponse(**response_data(**changes))


@pytest.mark.parametrize("scan_complete,graph_complete", [(True, True), (True, False), (False, True), (False, False)])
def test_component_and_overall_completeness_cannot_disagree(scan_complete, graph_complete):
    combined = scan_complete and graph_complete
    data = response_data(scan_complete=scan_complete, graph_complete=graph_complete, complete=combined)
    assert ScanResponse(**data).complete is combined
    with pytest.raises(ValidationError):
        ScanResponse(**{**data, "complete": not combined})


def test_diagnostics_are_separate_and_do_not_allow_complete_coverage():
    scan = Diagnostic(code="syntax_error", location=SourceLocation(file_path="broken.py", line_number=2))
    graph = Diagnostic(code="source_syntax_error", location=scan.location)
    data = response_data(scan_complete=False, graph_complete=False, complete=False,
                         scan_diagnostics=[scan], graph_diagnostics=[graph])
    response = ScanResponse(**data)
    payload = response.model_dump(mode="json")
    assert payload["scan_diagnostics"][0]["code"] == "syntax_error"
    assert payload["graph_diagnostics"][0]["code"] == "source_syntax_error"
    assert ScanResponse.model_validate_json(response.model_dump_json()) == response
    with pytest.raises(ValidationError):
        ScanResponse(**{**data, "scan_complete": True})


def test_empty_unknown_framework_and_unavailable_metadata_remain_null():
    response = ScanResponse(**response_data(
        nodes=[], graph_edges=[], scanned_files_count=0, discovered_files_count=0,
        total_source_bytes_read=0, detected_framework=None,
    ))
    assert response.model_dump(mode="json")["detected_framework"] is None
    with pytest.raises(ValidationError):
        ScanResponse(**{**response_data(), "nodes": [], "graph_edges": []})


@pytest.mark.parametrize("timestamp", [None, 0, True, datetime(2026, 10, 28), "2026-10-28", "2026-10-28T12:00:00", "invalid"])
def test_timestamp_must_be_supplied_and_timezone_aware(timestamp):
    with pytest.raises(ValidationError):
        ScanResponse(**response_data(timestamp=timestamp))


def test_transport_metadata_is_required_and_timezone_normalized():
    data = response_data(timestamp=datetime(2026, 10, 28, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    assert ScanResponse(**data).model_dump(mode="json")["timestamp"] == "2026-10-28T12:00:00.000000Z"
    for field in ("analysis_id", "timestamp", "data_source", "detected_framework"):
        with pytest.raises(ValidationError):
            ScanResponse(**{key: value for key, value in data.items() if key != field})


@pytest.mark.parametrize("code", list(DIAGNOSTIC_MESSAGES))
def test_all_controlled_diagnostics_round_trip(code):
    diagnostic = Diagnostic(code=code)
    assert Diagnostic.model_validate_json(diagnostic.model_dump_json()) == diagnostic
    assert diagnostic.message == DIAGNOSTIC_MESSAGES[code]


@pytest.mark.parametrize("model,code", [(Diagnostic, "syntax_error"), (ErrorResponse, "internal_error")])
def test_public_messages_cannot_accept_arbitrary_exception_or_sensitive_text(model, code):
    private = "PRIVATE_EXCEPTION_PROMPT_AND_CREDENTIAL_TEXT"
    with pytest.raises(ValidationError) as error:
        model(code=code, message=private)
    assert private not in str(error.value)
    with pytest.raises(ValidationError):
        model(code=private, message=private, **({"level": "error"} if model is Diagnostic else {}))
    with pytest.raises(ValidationError):
        model(code=code, exception=private)


def test_diagnostic_severity_location_and_catalog_are_controlled():
    assert Diagnostic(code="syntax_error").level == "error"
    assert Diagnostic(code="edge_limit").level == "warning"
    with pytest.raises(ValidationError):
        Diagnostic(code="syntax_error", level="warning")
    with pytest.raises(ValidationError):
        SourceLocation(file_path="app.py", column_number=0)
    with pytest.raises(TypeError):
        DIAGNOSTIC_MESSAGES["injected"] = "PRIVATE"


@pytest.mark.parametrize("code", list(ERROR_MESSAGES))
def test_safe_error_serialization(code):
    error = ErrorResponse(code=code)
    assert error.model_dump(mode="json") == {
        "schema_version": API_SCHEMA_VERSION, "code": code,
        "message": ERROR_MESSAGES[code], "request_id": None,
    }
    assert ErrorResponse.model_validate_json(error.model_dump_json()) == error


def test_error_request_id_and_response_collections_are_strict():
    error = ErrorResponse(code="internal_error", request_id="req_" + "a" * 32)
    assert error.request_id is not None
    with pytest.raises(ValidationError):
        ErrorResponse(code="internal_error", request_id="PRIVATE_TOKEN")
    response = ScanResponse(**response_data())
    with pytest.raises(ValidationError):
        response.complete = False
    assert isinstance(response.nodes, tuple) and isinstance(response.graph_edges, tuple)
    assert isinstance(response.graph_edges[0], tuple)


def test_catalog_covers_actual_compiler_diagnostics_without_importing_fixtures():
    root = Path(__file__).resolve().parents[2]
    seen = set()
    for relative in ("backend/compiler/ast_scanner.py", "backend/compiler/dag_builder.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not call.args:
                continue
            fn = call.func
            report = isinstance(fn, ast.Attribute) and fn.attr == "report"
            diagnostic = isinstance(fn, ast.Name) and fn.id in ("ScanDiagnostic", "GraphDiagnostic")
            barrier = isinstance(fn, ast.Attribute) and fn.attr == "barrier" and len(call.args) > 1
            candidate = call.args[1] if barrier else call.args[0]
            if (report or diagnostic or barrier) and isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                seen.add(candidate.value)
    assert seen <= DIAGNOSTIC_MESSAGES.keys()


def test_json_schema_is_serializable_and_describes_strict_public_fields():
    response_schema = ScanResponse.model_json_schema(mode="serialization")
    request_schema = ScanRequest.model_json_schema()
    assert response_schema["additionalProperties"] is False
    assert request_schema["additionalProperties"] is False
    assert response_schema["properties"]["schema_version"]["const"] == API_SCHEMA_VERSION
    assert "expected_schema" not in response_schema["$defs"]["LLMNode"]["properties"]
    assert "syntax_error" in response_schema["$defs"]["Diagnostic"]["properties"]["code"]["enum"]
    json.dumps(response_schema)


@pytest.mark.parametrize("field,diagnostic", [
    ("scan_diagnostics", "edge_limit"), ("graph_diagnostics", "syntax_error"),
])
def test_diagnostic_collections_reject_wrong_component_codes(field, diagnostic):
    with pytest.raises(ValidationError):
        ScanResponse(**response_data(scan_complete=False, graph_complete=False, complete=False,
                                     **{field: [Diagnostic(code=diagnostic)]}))


@pytest.mark.parametrize("field,value", [
    ("nodes", [None] * 20_001), ("graph_edges", [None] * 10_001),
    ("scan_diagnostics", [None] * 50_001), ("graph_diagnostics", [None] * 1_001),
])
def test_public_collection_budgets_reject_before_nested_processing(field, value):
    with pytest.raises(ValidationError, match="bounded array"):
        ScanResponse(**response_data(**{field: value}))


@pytest.mark.parametrize("name", ["PRIVATE SOURCE TEXT", "raise RuntimeError('PRIVATE')", "a\nb", "name."])
def test_function_metadata_cannot_contain_arbitrary_source_text(name):
    with pytest.raises(ValidationError):
        LLMNode(**node_data(function_name=name))


def test_function_metadata_preserves_existing_scanner_name_prefixes():
    prefix = "a" * 255 + "."
    assert LLMNode(**node_data(function_name=prefix)).function_name == prefix
    assert LLMNode(**node_data(function_name="outer.inner")).function_name == "outer.inner"


def test_actual_scanner_metadata_fits_the_public_node_contract(tmp_path):
    from backend.compiler.ast_scanner import scan_repository

    (tmp_path / "app.py").write_text('''from openai import OpenAI
client = OpenAI()
result = client.chat.completions.create(
    model=MODEL, messages=MESSAGES,
    response_format={"type": "json_schema", "json_schema": {"schema": OUTPUT_SCHEMA}}
)
''', encoding="utf-8")
    scan = scan_repository(str(tmp_path))
    assert scan.complete and len(scan.nodes) == 1
    internal = scan.nodes[0]
    node = LLMNode(
        node_id=internal.node_id, file_path=internal.file_path, line_number=internal.line_number,
        column_number=internal.column_number, current_model=internal.current_model,
        call_signature=internal.call_signature, function_name=internal.function_name,
        model_resolution=internal.model.kind, model_reference=internal.model.reference,
        model_references=internal.model.references, prompt_resolution=internal.messages.kind,
        prompt_reference=internal.messages.reference, prompt_references=internal.messages.references,
        schema_resolution=internal.response_format.kind, schema_reference=internal.response_format.reference,
        schema_references=internal.response_format.references,
        limited_schema_summary=LimitedSchemaSummary(
            format_type=internal.response_format.value["type"],
            schema_shape=SchemaShapeSummary(**internal.response_format.value["schema"]),
        ),
    )
    assert node.node_id == internal.node_id and node.current_model is None
    assert node.model_resolution == "reference"
    assert node.schema_resolution == "unresolved"
    assert node.limited_schema_summary.schema_shape.reference == "OUTPUT_SCHEMA"
