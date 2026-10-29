"""Bounded-concurrency benchmark of every node x model x case."""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from backend.compiler.ast_scanner import DiscoveredCall
from backend.compiler.cases import BenchmarkCase, CasesError, load_cases
from backend.compiler.evaluator import EvaluationResult, evaluate
from backend.compiler.metrics import estimate_cost
from backend.compiler.prompt_capture import CaptureResult, capture_requests
from backend.compiler.router_optimizer import select_model
from backend.config import ModelSpec, Settings
from backend.schemas import BenchmarkMetric, BenchmarkRun, NodeBenchmarkResult
from backend.services.llm import CompletionResult, LLMClient, LLMError

logger = logging.getLogger(__name__)

NO_CASES_ERROR = "No benchmark cases for this node in cascade_cases.yaml"
VACUOUS_CASE_ERROR = (
    "case has no assertions (add expected, must_include, must_not_include or a length bound)"
)


def case_is_vacuous(call: DiscoveredCall, case: BenchmarkCase) -> bool:
    """True when a case would accept any non-empty answer, which proves nothing."""
    if case.expected is not None or case.must_include or case.must_not_include:
        return False
    if case.min_chars is not None or case.max_chars is not None:
        return False
    # A JSON schema with required fields or enums is itself an assertion.
    schema = call.expected_schema or {}
    return not (schema.get("required") or schema.get("properties"))


@dataclass
class CallOutcome:
    completion: Optional[CompletionResult]
    evaluation: Optional[EvaluationResult]
    hard_ok: bool
    error: Optional[str] = None


@dataclass
class RunExtras:
    """Benchmark details kept beside the public BenchmarkRun."""

    repo_root: Path
    node_ids: list[str]
    threshold: float
    hard_ok: dict[str, dict[str, bool]] = field(default_factory=dict)  # node -> model -> ok
    spent_usd: float = 0.0


def _failed_metric(spec: ModelSpec, errors: list[str]) -> BenchmarkMetric:
    return BenchmarkMetric(
        model_id=spec.id, model_name=spec.name, tier=spec.tier, input_tokens=0, output_tokens=0,
        total_latency_ms=0.0, time_to_first_token_ms=None, estimated_cost_usd=0.0, quality_score=0.0,
        passes_validation=False, validation_errors=errors, is_estimated=False, status="failed",
    )


def aggregate_metric(spec: ModelSpec, outcomes: list[CallOutcome], threshold: float) -> tuple[BenchmarkMetric, bool]:
    """Fold per-case outcomes into one matrix cell. Returns (metric, hard_checks_ok)."""
    succeeded = [o for o in outcomes if o.completion is not None and o.evaluation is not None]
    errors: list[str] = []
    for i, o in enumerate(outcomes, start=1):
        prefix = f"case {i}: " if len(outcomes) > 1 else ""
        if o.error:
            errors.append(prefix + o.error)
        elif o.evaluation is not None:
            errors.extend(prefix + e for e in o.evaluation.validation_errors)
    if not succeeded:
        return _failed_metric(spec, errors or ["all calls failed"]), False

    completions = [o.completion for o in succeeded]
    costs = [estimate_cost(spec, c.input_tokens, c.output_tokens) for c in completions]
    ttfts = [c.time_to_first_token_ms for c in completions if c.time_to_first_token_ms is not None]
    # Failed calls count as quality 0 so flaky models are not rewarded.
    quality = sum(o.evaluation.quality_score for o in succeeded) / len(outcomes)
    hard_ok = len(succeeded) == len(outcomes) and all(o.hard_ok for o in outcomes)
    passes = hard_ok and quality >= threshold
    if not passes and quality < threshold and not any(e.startswith("Quality score") for e in errors):
        errors.insert(0, f"Mean quality {quality:.2f} below {threshold:.2f} threshold")

    metric = BenchmarkMetric(
        model_id=spec.id,
        model_name=spec.name,
        tier=spec.tier,
        input_tokens=round(statistics.mean(c.input_tokens for c in completions)),
        output_tokens=round(statistics.mean(c.output_tokens for c in completions)),
        total_latency_ms=round(statistics.median(c.total_latency_ms for c in completions), 1),
        time_to_first_token_ms=round(statistics.median(ttfts), 1) if ttfts else None,
        estimated_cost_usd=statistics.mean(costs),
        quality_score=round(min(1.0, max(0.0, quality)), 4),
        passes_validation=passes,
        validation_errors=list(dict.fromkeys(errors)),
        is_estimated=any(not c.usage_reported for c in completions),
        status="completed",
    )
    return metric, hard_ok


def _evaluate_case(call: DiscoveredCall, case: BenchmarkCase, text: str, threshold: float) -> tuple[EvaluationResult, bool]:
    kwargs = dict(
        expected_schema=call.expected_schema,
        json_required=call.json_required,
        reference=case.expected,
        must_include=case.must_include or None,
        must_not_include=case.must_not_include or None,
        min_chars=case.min_chars,
        max_chars=case.max_chars,
    )
    result = evaluate(text, threshold=threshold, **kwargs)
    hard_ok = evaluate(text, threshold=0.0, **kwargs).passes_validation
    return result, hard_ok


class BenchmarkRunner:
    def __init__(
        self,
        settings: Settings,
        client: LLMClient,
        capture: Callable[[Path, DiscoveredCall, list[BenchmarkCase], float], list[CaptureResult]] = capture_requests,
    ):
        self.settings = settings
        self.client = client
        self.capture = capture

    async def run(self, run: BenchmarkRun, extras: RunExtras, calls: list[DiscoveredCall]) -> None:
        """Fill `run` in place; never raises (errors are reported on the run)."""
        try:
            await self._run(run, extras, calls)
        except Exception as exc:  # report, don't crash the server task
            logger.exception("benchmark %s failed", run.run_id)
            run.status = "error"
            run.current_step = f"Benchmark failed: {exc}"

    async def _run(self, run: BenchmarkRun, extras: RunExtras, calls: list[DiscoveredCall]) -> None:
        settings, models = self.settings, list(self.settings.models)
        run.status = "running"
        run.current_step = "Loading benchmark cases"
        try:
            all_cases = load_cases(extras.repo_root)
        except CasesError as exc:
            run.status = "error"
            run.current_step = f"Invalid cascade_cases.yaml: {exc}"
            return

        captures: dict[str, list[CaptureResult]] = {}
        for i, call in enumerate(calls, start=1):
            cases = all_cases.get(call.node_id, [])
            run.current_step = f"Capturing prompts for {call.node_id} ({i}/{len(calls)})"
            try:
                captured = await asyncio.to_thread(
                    self.capture, extras.repo_root, call, cases, settings.regression_timeout_seconds
                )
            except (TypeError, ValueError) as exc:  # one node's bad input must not sink the run
                captured = [CaptureResult(None, f"prompt capture failed: {exc}")] * len(cases)
            # Vacuous cases are never sent to a model: they would make any answer "pass".
            captures[call.node_id] = [
                CaptureResult(None, VACUOUS_CASE_ERROR) if case_is_vacuous(call, case) else cap
                for case, cap in zip(cases, captured)
            ]

        jobs = [
            (call, case_idx, spec)
            for call in calls
            for case_idx, cap in enumerate(captures[call.node_id])
            if cap.ok
            for spec in models
        ]
        total = len(jobs)
        done = 0
        outcomes: dict[tuple[str, str], list[Optional[CallOutcome]]] = {
            (call.node_id, spec.id): [None] * len(captures[call.node_id]) for call in calls for spec in models
        }
        # Capture failures become per-case errors for every model.
        for call in calls:
            for idx, cap in enumerate(captures[call.node_id]):
                if not cap.ok:
                    for spec in models:
                        outcomes[(call.node_id, spec.id)][idx] = CallOutcome(None, None, False, cap.error)

        semaphore = asyncio.Semaphore(settings.benchmark_concurrency)
        cases_by_node = {call.node_id: all_cases.get(call.node_id, []) for call in calls}

        async def execute(call: DiscoveredCall, idx: int, spec: ModelSpec) -> None:
            nonlocal done
            request = captures[call.node_id][idx].request
            assert request is not None
            async with semaphore:
                run.current_step = f"{spec.name} × {call.node_id} (case {idx + 1})"
                try:
                    completion = await asyncio.wait_for(
                        self.client.complete(spec.id, request.messages, request.params),
                        timeout=settings.benchmark_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    outcome = CallOutcome(None, None, False, f"timed out after {settings.benchmark_timeout_seconds:g}s")
                except LLMError as exc:
                    outcome = CallOutcome(None, None, False, str(exc))
                except Exception as exc:  # one bad call must not abort the whole run
                    logger.exception("benchmark call %s/%s failed", call.node_id, spec.id)
                    outcome = CallOutcome(None, None, False, f"{spec.id}: unexpected error: {type(exc).__name__}")
                else:
                    extras.spent_usd += estimate_cost(spec, completion.input_tokens, completion.output_tokens)
                    try:
                        evaluation, hard_ok = _evaluate_case(
                            call, cases_by_node[call.node_id][idx], completion.text, extras.threshold
                        )
                    except Exception as exc:  # e.g. a malformed schema in the target repo
                        logger.exception("evaluation failed for %s/%s", call.node_id, spec.id)
                        outcome = CallOutcome(None, None, False, f"evaluation failed: {type(exc).__name__}: {exc}")
                    else:
                        outcome = CallOutcome(completion, evaluation, hard_ok)
            outcomes[(call.node_id, spec.id)][idx] = outcome
            done += 1
            run.progress_pct = round(done / total * 100, 1)

        await asyncio.gather(*(execute(call, idx, spec) for call, idx, spec in jobs))

        run.nodes = []
        for call in calls:
            metrics: dict[str, BenchmarkMetric] = {}
            node_hard: dict[str, bool] = {}
            for spec in models:
                cell = [o for o in outcomes[(call.node_id, spec.id)] if o is not None]
                if not cell:
                    metrics[spec.id] = _failed_metric(spec, [NO_CASES_ERROR])
                    node_hard[spec.id] = False
                    continue
                metrics[spec.id], node_hard[spec.id] = aggregate_metric(spec, cell, extras.threshold)
            extras.hard_ok[call.node_id] = node_hard
            run.nodes.append(
                NodeBenchmarkResult(
                    node_id=call.node_id,
                    metrics_by_model=metrics,
                    recommended_model_id=select_model(metrics, extras.threshold, node_hard),
                )
            )
        run.progress_pct = 100.0
        run.status = "complete"
        evaluated = sum(1 for o in outcomes.values() for x in o if x and x.completion)
        run.current_step = f"Completed {evaluated} model evaluations across {len(calls)} nodes"
