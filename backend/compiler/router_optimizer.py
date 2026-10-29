"""Lowest-cost model selection: min(cost) s.t. quality >= threshold and hard checks pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from backend.compiler.metrics import cost_savings_pct, latency_reduction_pct
from backend.config import Settings
from backend.schemas import BenchmarkMetric, DecisionStatus, LLMNode, NodeBenchmarkResult

TIER_RANK = {"efficient": 0, "balanced": 1, "powerful": 2}
# Two candidates within this relative cost difference are tie-broken on latency.
COST_TIE_PCT = 2.0
# More than this share of failed model runs makes a node inconclusive.
MAX_FAILED_SHARE = 0.5


def is_candidate(metric: BenchmarkMetric, threshold: float, hard_ok: Optional[bool]) -> bool:
    if metric.status != "completed":
        return False
    checks_ok = metric.passes_validation if hard_ok is None else hard_ok
    return checks_ok and metric.quality_score >= threshold


def select_model(
    metrics: Mapping[str, BenchmarkMetric],
    threshold: float,
    hard_ok: Optional[Mapping[str, bool]] = None,
) -> Optional[str]:
    """Cheapest passing model; near-ties (<2% cost) go to the lower latency."""
    candidates = [
        m for model_id, m in metrics.items()
        if is_candidate(m, threshold, None if hard_ok is None else hard_ok.get(model_id, False))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda m: (m.estimated_cost_usd, m.total_latency_ms, m.model_id))
    cheapest = candidates[0]
    # The tie window is measured from the cheapest model, never from a moving best,
    # so the pick is at most COST_TIE_PCT more expensive than the cheapest pass.
    limit = cheapest.estimated_cost_usd * (1 + COST_TIE_PCT / 100)
    near_ties = [m for m in candidates if m.estimated_cost_usd < limit] or [cheapest]
    return min(near_ties, key=lambda m: (m.total_latency_ms, m.estimated_cost_usd, m.model_id)).model_id


@dataclass(frozen=True)
class NodeDecision:
    node_id: str
    baseline_model: str
    recommended_model: str
    fallback_model: str
    baseline_cost_usd: float
    optimized_cost_usd: float
    cost_reduction_pct: float
    baseline_latency_ms: float
    optimized_latency_ms: float
    latency_reduction_pct: float
    quality_score: float
    status: DecisionStatus
    reason: str


def _fallback_for(
    chosen: BenchmarkMetric,
    metrics: Mapping[str, BenchmarkMetric],
    threshold: float,
    hard_ok: Optional[Mapping[str, bool]],
    settings: Settings,
) -> str:
    rank = TIER_RANK[chosen.tier]
    higher = [
        m for model_id, m in metrics.items()
        if TIER_RANK[m.tier] > rank
        and is_candidate(m, threshold, None if hard_ok is None else hard_ok.get(model_id, False))
    ]
    if higher:
        return min(higher, key=lambda m: (m.estimated_cost_usd, m.model_id)).model_id
    # Escalate to the frontier tier, unless that is the chosen model itself.
    if settings.powerful_model.id != chosen.model_id:
        return settings.powerful_model.id
    return chosen.model_id


def decide_node(
    node: LLMNode,
    result: NodeBenchmarkResult,
    threshold: float,
    settings: Settings,
    hard_ok: Optional[Mapping[str, bool]] = None,
) -> NodeDecision:
    metrics = result.metrics_by_model
    powerful = settings.powerful_model.id
    baseline_id = node.current_model if node.current_model in metrics else powerful
    baseline = metrics.get(baseline_id)

    def retained(status: DecisionStatus, reason: str) -> NodeDecision:
        cost = baseline.estimated_cost_usd if baseline else 0.0
        latency = baseline.total_latency_ms if baseline else 0.0
        quality = baseline.quality_score if baseline else 0.0
        return NodeDecision(
            node_id=node.node_id, baseline_model=baseline_id, recommended_model=baseline_id,
            fallback_model=powerful, baseline_cost_usd=cost, optimized_cost_usd=cost,
            cost_reduction_pct=0.0, baseline_latency_ms=latency, optimized_latency_ms=latency,
            latency_reduction_pct=0.0, quality_score=quality, status=status, reason=reason,
        )

    if baseline is None or baseline.status != "completed":
        return retained("inconclusive", "baseline model was not benchmarked successfully")
    failed = sum(1 for m in metrics.values() if m.status == "failed")
    if metrics and failed / len(metrics) > MAX_FAILED_SHARE:
        return retained("inconclusive", f"{failed} of {len(metrics)} model runs failed")

    chosen_id = select_model(metrics, threshold, hard_ok)
    if chosen_id is None:
        return retained("baseline_retained", f"no model meets quality >= {threshold:g}")
    chosen = metrics[chosen_id]
    if chosen_id == baseline_id or chosen.estimated_cost_usd >= baseline.estimated_cost_usd:
        return retained("baseline_retained", "no passing model is cheaper than the baseline")

    return NodeDecision(
        node_id=node.node_id,
        baseline_model=baseline_id,
        recommended_model=chosen_id,
        fallback_model=_fallback_for(chosen, metrics, threshold, hard_ok, settings),
        baseline_cost_usd=baseline.estimated_cost_usd,
        optimized_cost_usd=chosen.estimated_cost_usd,
        cost_reduction_pct=round(cost_savings_pct(baseline.estimated_cost_usd, chosen.estimated_cost_usd) or 0.0, 2),
        baseline_latency_ms=baseline.total_latency_ms,
        optimized_latency_ms=chosen.total_latency_ms,
        latency_reduction_pct=round(
            latency_reduction_pct(baseline.total_latency_ms, chosen.total_latency_ms) or 0.0, 2
        ),
        quality_score=chosen.quality_score,
        status="optimized",
        reason=f"{chosen.model_name} is the cheapest model meeting quality >= {threshold:g}",
    )
