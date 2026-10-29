"""FinOps cost and latency calculations.

Cost = (tokens_in / 1e6) * price_in + (tokens_out / 1e6) * price_out
Savings % = (baseline - optimized) / baseline * 100
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from backend.config import ModelSpec

TOKENS_PER_MILLION = 1_000_000
# Rough chars-per-token ratio used only when the API omits `usage`.
CHARS_PER_TOKEN = 4


def estimate_cost(spec: ModelSpec, input_tokens: int, output_tokens: int) -> float:
    """Exact USD cost of one call given token counts and catalog prices."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    return (
        input_tokens / TOKENS_PER_MILLION * spec.input_price_per_m
        + output_tokens / TOKENS_PER_MILLION * spec.output_price_per_m
    )


def estimate_tokens(text: str) -> int:
    """Heuristic token count for text when the provider gives no usage data."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def reduction_pct(baseline: float | None, optimized: float | None) -> float | None:
    """Percentage reduction from baseline to optimized.

    Returns None when either value is missing or the baseline is not positive,
    so callers never display a fabricated 0%.
    """
    if baseline is None or optimized is None:
        return None
    if not math.isfinite(baseline) or not math.isfinite(optimized) or baseline <= 0:
        return None
    return (baseline - optimized) / baseline * 100.0


def cost_savings_pct(baseline_cost: float | None, optimized_cost: float | None) -> float | None:
    return reduction_pct(baseline_cost, optimized_cost)


def latency_reduction_pct(baseline_ms: float | None, optimized_ms: float | None) -> float | None:
    return reduction_pct(baseline_ms, optimized_ms)


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (same as numpy's default), p in [0, 100]."""
    if not values:
        raise ValueError("percentile of empty sequence")
    if not 0 <= p <= 100:
        raise ValueError("p must be within [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * p / 100.0
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


@dataclass(frozen=True)
class LatencySummary:
    median_ms: float
    p95_ms: float
    mean_ms: float
    samples: int


def summarize_latencies(values: Iterable[float]) -> LatencySummary:
    samples = [float(v) for v in values]
    if not samples:
        raise ValueError("no latency samples")
    if any(v < 0 or not math.isfinite(v) for v in samples):
        raise ValueError("latency samples must be finite and non-negative")
    return LatencySummary(
        median_ms=percentile(samples, 50),
        p95_ms=percentile(samples, 95),
        mean_ms=sum(samples) / len(samples),
        samples=len(samples),
    )


@dataclass(frozen=True)
class DecisionTotals:
    total_baseline_cost_usd: float
    total_optimized_cost_usd: float
    total_cost_reduction_pct: float
    avg_latency_reduction_pct: float


def aggregate_totals(
    decisions: Iterable[tuple[float, float, float, float]],
) -> DecisionTotals:
    """Totals across nodes.

    Each item is (baseline_cost, optimized_cost, baseline_latency_ms, optimized_latency_ms).
    Cost reduction is computed over summed costs; latency reduction is the mean of
    per-node reductions for nodes with a defined baseline. Empty input yields zeros,
    which is a true statement: nothing was optimized.
    """
    items = list(decisions)
    total_base = sum(d[0] for d in items)
    total_opt = sum(d[1] for d in items)
    cost_pct = reduction_pct(total_base, total_opt)
    latency_pcts = [
        pct for pct in (latency_reduction_pct(d[2], d[3]) for d in items) if pct is not None
    ]
    return DecisionTotals(
        total_baseline_cost_usd=total_base,
        total_optimized_cost_usd=total_opt,
        total_cost_reduction_pct=cost_pct if cost_pct is not None else 0.0,
        avg_latency_reduction_pct=sum(latency_pcts) / len(latency_pcts) if latency_pcts else 0.0,
    )
