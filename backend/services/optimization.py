"""Turn a completed benchmark run into an OptimizeResult (decisions, policy, patch, regression)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from backend.compiler.ast_scanner import DiscoveredCall
from backend.compiler.metrics import aggregate_totals
from backend.compiler.patch_generator import build_patches, node_diff
from backend.compiler.policy_generator import build_policy, dump_node_policy, dump_policy
from backend.compiler.regression_runner import RegressionResult, run_regression
from backend.compiler.router_optimizer import NodeDecision, decide_node
from backend.config import REPO_ROOT, Settings
from backend.schemas import OptimizationDecision, OptimizeResult
from backend.store import StoredRun

logger = logging.getLogger(__name__)


class OptimizeError(ValueError):
    """The run cannot be optimized (e.g. not complete)."""


@dataclass
class _NodeContext:
    call: DiscoveredCall
    decision: NodeDecision


def _display_repo(stored: StoredRun) -> str:
    root = stored.extras.repo_root
    try:
        return root.relative_to(REPO_ROOT).as_posix() or "."
    except ValueError:
        return root.name


def optimize_run(
    stored: StoredRun,
    threshold: float,
    settings: Settings,
    regression: Optional[Callable[..., RegressionResult]] = None,
) -> OptimizeResult:
    """Pure orchestration; `regression` is injectable for tests (defaults to the sandbox)."""
    run = stored.run
    if run.status != "complete":
        raise OptimizeError(f"benchmark run is {run.status}; wait until it is complete")
    regression = regression or run_regression

    calls = {c.node_id: c for c in stored.scan.repo.calls}
    nodes = {n.node_id: n for n in stored.scan.result.nodes}
    contexts: list[_NodeContext] = []
    for result in run.nodes:
        call, node = calls.get(result.node_id), nodes.get(result.node_id)
        if call is None or node is None:
            continue
        decision = decide_node(node, result, threshold, settings, stored.extras.hard_ok.get(result.node_id))
        contexts.append(_NodeContext(call, decision))

    totals = aggregate_totals(
        (c.decision.baseline_cost_usd, c.decision.optimized_cost_usd,
         c.decision.baseline_latency_ms, c.decision.optimized_latency_ms)
        for c in contexts
    )
    policy = build_policy(
        ((c.decision, c.call.expected_schema, c.call.json_required) for c in contexts),
        threshold=threshold,
        repository=_display_repo(stored),
        run_id=run.run_id,
        data_source=run.data_source,
        total_cost_reduction_pct=(
            round(totals.total_cost_reduction_pct, 2) if totals.total_cost_reduction_pct is not None else None
        ),
    )
    policy_text = dump_policy(policy)

    optimized = [c.call for c in contexts if c.decision.status == "optimized"]
    sources = stored.scan.repo.sources
    patches = build_patches(sources, optimized)

    regression_result: Optional[RegressionResult] = None
    if patches.files:
        regression_result = regression(
            stored.extras.repo_root, patches, policy_text, settings.regression_timeout_seconds
        )

    decisions: list[OptimizationDecision] = []
    for ctx in contexts:
        d = ctx.decision
        patch_error = patches.errors.get(d.node_id)
        if d.status != "optimized":
            diff, passed, log = "", True, f"No code change: {d.reason}"
        elif patch_error:
            diff, passed, log = "", False, f"Patch could not be generated: {patch_error}"
        else:
            diff = node_diff(sources, ctx.call) or ""
            assert regression_result is not None
            passed = regression_result.passed
            log = regression_result.log_for(ctx.call.function_name)
        decisions.append(
            OptimizationDecision(
                node_id=d.node_id,
                baseline_model=d.baseline_model,
                recommended_model=d.recommended_model,
                fallback_model=d.fallback_model,
                baseline_cost_usd=d.baseline_cost_usd,
                optimized_cost_usd=d.optimized_cost_usd,
                cost_reduction_pct=d.cost_reduction_pct,
                baseline_latency_ms=d.baseline_latency_ms,
                optimized_latency_ms=d.optimized_latency_ms,
                latency_reduction_pct=d.latency_reduction_pct,
                quality_score=d.quality_score,
                status=d.status,
                policy_yaml=dump_node_policy(d.node_id, policy["nodes"][d.node_id]),
                patch_diff=diff,
                regression_passed=passed,
                regression_log=log,
            )
        )

    all_passed = all(d.regression_passed for d in decisions) and (
        regression_result is None or regression_result.passed
    )
    return OptimizeResult(
        decisions=decisions,
        total_baseline_cost_usd=totals.total_baseline_cost_usd,
        total_optimized_cost_usd=totals.total_optimized_cost_usd,
        # The contract requires numbers; an undefined reduction (nothing measured) is 0.
        total_cost_reduction_pct=round(totals.total_cost_reduction_pct or 0.0, 2),
        avg_latency_reduction_pct=round(totals.avg_latency_reduction_pct or 0.0, 2),
        combined_policy_yaml=policy_text,
        combined_patch_diff=patches.combined_diff(),
        all_regressions_passed=all_passed,
        data_source=run.data_source,
    )
