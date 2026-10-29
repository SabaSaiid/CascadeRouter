import pytest
from pydantic import ValidationError

from backend.schemas import BenchmarkMetric, BenchmarkRequest, LLMNode, OptimizeRequest, ScanResult


def _metric(**over):
    base = dict(
        model_id="m", model_name="M", tier="efficient", input_tokens=1, output_tokens=1,
        total_latency_ms=1.0, estimated_cost_usd=0.0, quality_score=1.0,
        passes_validation=True, is_estimated=False, status="completed",
    )
    base.update(over)
    return BenchmarkMetric(**base)


def test_graph_edges_serialise_as_arrays():
    node = LLMNode(node_id="a", file_path="x.py", line_number=1, current_model="m", call_signature="c()")
    scan = ScanResult(
        repository_path="r", nodes=[node], graph_edges=[("a", "b")], timestamp="t",
        data_source="live", scanned_files_count=1, detected_framework="openai",
    )
    assert scan.model_dump(mode="json")["graph_edges"] == [["a", "b"]]


def test_optional_fields_default_to_none():
    node = LLMNode(node_id="a", file_path="x.py", line_number=1, current_model="m", call_signature="c()")
    assert node.expected_schema is None and node.snippet is None
    assert _metric().time_to_first_token_ms is None
    assert _metric().validation_errors == []


@pytest.mark.parametrize(
    "over",
    [{"tier": "huge"}, {"quality_score": 1.2}, {"input_tokens": -1}, {"status": "done"}, {"extra": 1}],
)
def test_metric_rejects_invalid(over):
    with pytest.raises(ValidationError):
        _metric(**over)


def test_requests_validate():
    with pytest.raises(ValidationError):
        BenchmarkRequest(node_ids=[])
    with pytest.raises(ValidationError):
        OptimizeRequest(run_id="r", quality_threshold=2)
    assert OptimizeRequest(run_id="r").quality_threshold == 0.92
