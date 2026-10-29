"""Read-only projection of the existing compiler into the shared API schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from backend.compiler.dag_builder import ProvisionalAnalysisResult, analyze_repository
from backend.schemas import Diagnostic, LLMNode, LimitedSchemaSummary, ScanResponse, SourceLocation
from .errors import ServiceError


def _diagnostic(item) -> Diagnostic:
    location = None
    if item.file_path not in (None, "."):
        location = SourceLocation(
            file_path=item.file_path, line_number=item.line_number,
            column_number=getattr(item, "column_number", None),
        )
    return Diagnostic(code=item.code, location=location)


def adapt_analysis(result: ProvisionalAnalysisResult, *, analysis_id: str, timestamp: datetime) -> ScanResponse:
    scan, graph = result.scan_result, result.workflow_graph
    identifiers = {node.node_id for node in scan.nodes}
    graph_ids = set(graph.node_ids)
    if (
        scan.repository_path != graph.repository_path
        or len(graph_ids) != len(graph.node_ids) or not graph_ids <= identifiers
        or (graph.complete and graph_ids != identifiers)
        or any(edge.kind != "data_dependency" or edge.from_node_id not in graph_ids
               or edge.to_node_id not in graph_ids for edge in graph.edges)
    ):
        raise ServiceError("source_conflict")
    try:
        nodes = []
        for node in scan.nodes:
            metadata = {}
            for public, internal in (("model", node.model), ("prompt", node.messages), ("schema", node.response_format)):
                metadata.update({public + "_resolution": internal.kind,
                                 public + "_reference": internal.reference,
                                 public + "_references": internal.references})
            summary = None
            value = node.response_format.value
            if value is not None:
                if type(value) is not dict or value.keys() - {"type", "strict", "schema"}:
                    raise ServiceError("source_conflict")
                summary = LimitedSchemaSummary(
                    format_type=value.get("type"), strict=value.get("strict"), schema_shape=value.get("schema"),
                )
            nodes.append(LLMNode(
                node_id=node.node_id, file_path=node.file_path, line_number=node.line_number,
                column_number=node.column_number, current_model=node.current_model,
                call_signature=node.call_signature, function_name=node.function_name,
                limited_schema_summary=summary, **metadata,
            ))
        return ScanResponse(
            analysis_id=analysis_id, timestamp=timestamp, repository_path=scan.repository_path,
            nodes=nodes, graph_edges=[(edge.from_node_id, edge.to_node_id) for edge in graph.edges],
            scanned_files_count=scan.scanned_files_count, discovered_files_count=scan.discovered_files_count,
            total_source_bytes_read=scan.total_source_bytes_read,
            detected_framework=("LiteLLM" if any(n.call_signature.startswith("litellm.") for n in nodes) else "OpenAI SDK") if nodes else None,
            data_source="live",
            scan_complete=scan.complete, graph_complete=graph.complete, complete=result.complete,
            scan_diagnostics=[_diagnostic(item) for item in scan.diagnostics],
            graph_diagnostics=[_diagnostic(item) for item in graph.diagnostics],
        )
    except (ValidationError, TypeError, ValueError):
        raise ServiceError("source_conflict") from None


def analyze_for_api(repository_path: str, *, analysis_id: str, timestamp: datetime) -> ScanResponse:
    return adapt_analysis(analyze_repository(repository_path), analysis_id=analysis_id, timestamp=timestamp)
