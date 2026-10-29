"""Shared Pydantic data contracts.

Mirrors `frontend/src/types.ts` field-for-field; `tests/api/test_contract.py`
fails if the two drift apart.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

DataSourceMode = Literal["live", "recorded", "mock"]
ModelTier = Literal["efficient", "balanced", "powerful"]
MetricStatus = Literal["completed", "failed", "running", "pending"]
RunStatus = Literal["idle", "running", "complete", "error"]
DecisionStatus = Literal["optimized", "inconclusive", "baseline_retained"]

GraphEdge = tuple[str, str]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class LLMNode(_Model):
    node_id: str
    file_path: str
    line_number: int = Field(ge=1)
    current_model: str
    call_signature: str
    prompt_reference: Optional[str] = None
    expected_schema: Optional[dict[str, Any]] = None
    function_name: Optional[str] = None
    docstring: Optional[str] = None
    snippet: Optional[str] = None


class ScanResult(_Model):
    repository_path: str
    nodes: list[LLMNode]
    graph_edges: list[GraphEdge]
    timestamp: str
    data_source: DataSourceMode
    scanned_files_count: int = Field(ge=0)
    detected_framework: str


class BenchmarkMetric(_Model):
    model_id: str
    model_name: str
    tier: ModelTier
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0)
    time_to_first_token_ms: Optional[float] = Field(default=None, ge=0)
    estimated_cost_usd: float = Field(ge=0)
    quality_score: float = Field(ge=0, le=1)
    passes_validation: bool
    validation_errors: list[str] = Field(default_factory=list)
    is_estimated: bool
    status: MetricStatus


class NodeBenchmarkResult(_Model):
    node_id: str
    metrics_by_model: dict[str, BenchmarkMetric]
    recommended_model_id: Optional[str] = None


class BenchmarkRun(_Model):
    run_id: str
    status: RunStatus
    progress_pct: float = Field(ge=0, le=100)
    current_step: Optional[str] = None
    nodes: list[NodeBenchmarkResult]
    data_source: DataSourceMode
    created_at: str


class OptimizationDecision(_Model):
    node_id: str
    baseline_model: str
    recommended_model: str
    fallback_model: str
    baseline_cost_usd: float = Field(ge=0)
    optimized_cost_usd: float = Field(ge=0)
    cost_reduction_pct: float
    baseline_latency_ms: float = Field(ge=0)
    optimized_latency_ms: float = Field(ge=0)
    latency_reduction_pct: float
    quality_score: float = Field(ge=0, le=1)
    status: DecisionStatus
    policy_yaml: str
    patch_diff: str
    regression_passed: bool
    regression_log: Optional[str] = None


class OptimizeResult(_Model):
    decisions: list[OptimizationDecision]
    total_baseline_cost_usd: float = Field(ge=0)
    total_optimized_cost_usd: float = Field(ge=0)
    total_cost_reduction_pct: float
    avg_latency_reduction_pct: float
    combined_policy_yaml: str
    combined_patch_diff: str
    all_regressions_passed: bool
    data_source: DataSourceMode


class ModelTierConfig(_Model):
    """Catalog entry; camelCase field names match `ModelTierConfig` in types.ts."""

    id: str
    name: str
    tier: ModelTier
    inputPricePerM: float = Field(ge=0)
    outputPricePerM: float = Field(ge=0)
    description: str
    badgeColor: str


# --------------------------------------------------------------------------- #
# Request / response bodies for the HTTP API                                  #
# --------------------------------------------------------------------------- #


class ScanRequest(_Model):
    repository_path: str = Field(min_length=1)


class BenchmarkRequest(_Model):
    node_ids: list[str] = Field(min_length=1)
    repository_path: Optional[str] = None


class BenchmarkStarted(_Model):
    run_id: str


class OptimizeRequest(_Model):
    run_id: str = Field(min_length=1)
    quality_threshold: float = Field(default=0.92, ge=0, le=1)


class HealthResponse(_Model):
    status: Literal["ok"]
    version: str
    environment: str
    data_source: DataSourceMode
    nebius_configured: bool
