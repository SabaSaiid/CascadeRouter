"""The public projection preserves compiler facts and cannot export source data."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from backend.compiler.ast_scanner import ScanDiagnostic
from backend.compiler.dag_builder import GraphOptions, analyze_repository
from backend.schemas import ScanResponse
from backend.services import compiler_adapter
from backend.services.errors import ServiceError


METADATA = {"analysis_id": "analysis_" + "a" * 32, "timestamp": datetime(2026, 10, 28, tzinfo=timezone.utc)}


def test_adapter_calls_compiler_once_preserves_identity_edges_counts_and_unknowns(api_environment, monkeypatch):
    _, repository, _ = api_environment
    actual = analyze_repository(str(repository))
    before = actual.to_dict()
    calls = []

    def compiler(path):
        calls.append(path)
        return actual

    monkeypatch.setattr(compiler_adapter, "analyze_repository", compiler)
    response = compiler_adapter.analyze_for_api(str(repository), **METADATA)
    assert calls == [str(repository)]
    assert actual.to_dict() == before
    assert [node.node_id for node in response.nodes] == [node.node_id for node in actual.scan_result.nodes]
    assert response.graph_edges == tuple((edge.from_node_id, edge.to_node_id) for edge in actual.workflow_graph.edges)
    assert len(response.graph_edges) == 1
    assert response.nodes[1].current_model is None
    assert response.nodes[1].model_resolution == "reference"
    assert response.nodes[1].model_reference == "MODEL"
    assert response.nodes[1].prompt_reference == "first"
    assert response.scanned_files_count == actual.scan_result.scanned_files_count
    assert response.discovered_files_count == actual.scan_result.discovered_files_count
    assert response.total_source_bytes_read == actual.scan_result.total_source_bytes_read
    assert response.complete and response.data_source == "live"
    assert response.analysis_id == METADATA["analysis_id"] and response.timestamp == METADATA["timestamp"]
    assert ScanResponse.model_validate_json(response.model_dump_json()) == response
    assert not {"source_fingerprints", "verified_sources", "evidence", "source", "snippet"} & response.model_dump().keys()


def test_separate_diagnostics_partial_graph_and_fixed_messages(api_environment):
    _, repository, _ = api_environment
    (repository / "broken.py").write_text("def invalid(:\n", encoding="utf-8")
    actual = analyze_repository(str(repository))
    actual = replace(actual, scan_result=replace(actual.scan_result, diagnostics=(
        ScanDiagnostic("syntax_error", "PRIVATE_EXCEPTION_SOURCE", "broken.py", 1),
    )))
    response = compiler_adapter.adapt_analysis(actual, **METADATA)
    assert not response.scan_complete and not response.graph_complete and not response.complete
    assert response.scan_diagnostics[0].code == "syntax_error"
    assert response.scan_diagnostics[0].location.file_path == "broken.py"
    assert "input_scan_incomplete" in {item.code for item in response.graph_diagnostics}
    assert "PRIVATE_EXCEPTION_SOURCE" not in response.model_dump_json()


def test_partial_graph_can_have_fewer_vertices_without_losing_scanner_nodes(api_environment):
    _, repository, _ = api_environment
    actual = analyze_repository(str(repository), graph_options=GraphOptions(max_nodes=1))
    response = compiler_adapter.adapt_analysis(actual, **METADATA)
    assert len(response.nodes) == 2 and response.scan_complete and not response.graph_complete


def test_response_format_is_only_limited_summary_and_expression_reference(api_environment):
    _, repository, _ = api_environment
    (repository / "app.py").write_text('''from openai import OpenAI
client = OpenAI()
def workflow():
    first = client.chat.completions.create(model="fixture/model", messages=build(PROMPT), response_format={"type":"json_schema", "json_schema":{"name":"PRIVATE_NAME", "strict":True, "schema":{"type":"object", "properties":{"secret":{"description":"PRIVATE_DESCRIPTION"}}, "required":["secret"]}}})
''', encoding="utf-8")
    response = compiler_adapter.analyze_for_api(str(repository), **METADATA)
    node = response.nodes[0]
    assert node.function_name == "workflow" and node.prompt_resolution == "unresolved"
    assert node.prompt_reference is None and "PROMPT" in node.prompt_references
    assert node.limited_schema_summary.format_type == "json_schema"
    assert node.limited_schema_summary.strict is True
    assert node.limited_schema_summary.schema_shape.property_count == 1
    assert "PRIVATE_" not in response.model_dump_json() and "expected_schema" not in response.model_dump_json()


@pytest.mark.parametrize("change", ["endpoint", "duplicate_graph", "repository", "complete_vertices", "unknown_diagnostic"])
def test_incompatible_compiler_state_is_rejected(api_environment, change):
    _, repository, _ = api_environment
    actual = analyze_repository(str(repository))
    graph = actual.workflow_graph
    if change == "endpoint":
        graph = replace(graph, edges=(replace(graph.edges[0], to_node_id="llm_" + "0" * 24),))
    elif change == "duplicate_graph":
        graph = replace(graph, node_ids=graph.node_ids * 2)
    elif change == "repository":
        graph = replace(graph, repository_path="PRIVATE_OTHER_ROOT")
    elif change == "complete_vertices":
        graph = replace(graph, node_ids=())
    else:
        actual = replace(actual, scan_result=replace(actual.scan_result, complete=False,
                         diagnostics=(ScanDiagnostic("UNKNOWN_PRIVATE_CODE", "PRIVATE_MESSAGE"),)))
    with pytest.raises(ServiceError) as error:
        compiler_adapter.adapt_analysis(replace(actual, workflow_graph=graph), **METADATA)
    assert error.value.code == "source_conflict" and "PRIVATE" not in str(error.value)
