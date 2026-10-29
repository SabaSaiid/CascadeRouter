import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.cases import BenchmarkCase
from backend.compiler.evaluator import EvaluationResult
from backend.compiler.prompt_capture import CapturedRequest, CaptureResult
from backend.compiler.shadow_runner import (
    NO_CASES_ERROR,
    VACUOUS_CASE_ERROR,
    BenchmarkRunner,
    CallOutcome,
    RunExtras,
    aggregate_metric,
    case_is_vacuous,
)
from backend.config import REPO_ROOT, load_settings
from backend.schemas import BenchmarkRun
from backend.services.llm import CompletionResult, LLMError

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"
S = load_settings()
NANO, LIGHT, SUPER, ULTRA = S.models


def comp(text="x", inp=100, out=10, latency=100.0, ttft=20.0, reported=True):
    return CompletionResult(text, inp, out, reported, latency, ttft)


def ok(score=1.0, hard=True):
    return CallOutcome(comp(), EvaluationResult(score, score >= 0.92 and hard, [] if hard else ["Missing required fields: x"]), hard)


# ---------------------------------------------------------------- aggregate_metric


def test_aggregate_all_pass():
    outcomes = [
        CallOutcome(comp(inp=100, out=10, latency=100, ttft=10), EvaluationResult(1.0, True), True),
        CallOutcome(comp(inp=300, out=30, latency=300, ttft=30), EvaluationResult(0.9, True), True),
        CallOutcome(comp(inp=200, out=20, latency=200, ttft=None, reported=False), EvaluationResult(1.0, True), True),
    ]
    metric, hard = aggregate_metric(NANO, outcomes, 0.92)
    assert hard and metric.passes_validation and metric.status == "completed"
    assert (metric.input_tokens, metric.output_tokens) == (200, 20)
    assert metric.total_latency_ms == 200 and metric.time_to_first_token_ms == 20
    assert metric.quality_score == pytest.approx(0.9667, abs=1e-4)
    expected_cost = sum((i / 1e6) * 0.06 + (o / 1e6) * 0.24 for i, o in [(100, 10), (300, 30), (200, 20)]) / 3
    assert metric.estimated_cost_usd == pytest.approx(expected_cost)
    assert metric.is_estimated is True  # one call had no usage


def test_aggregate_failed_call_counts_as_zero_quality():
    outcomes = [ok(), CallOutcome(None, None, False, "m: HTTP 500: boom")]
    metric, hard = aggregate_metric(SUPER, outcomes, 0.92)
    assert not hard and not metric.passes_validation and metric.status == "completed"
    assert metric.quality_score == 0.5
    assert "case 2: m: HTTP 500: boom" in metric.validation_errors
    assert metric.validation_errors[0] == "Mean quality 0.50 below 0.92 threshold"


def test_aggregate_all_failed():
    metric, hard = aggregate_metric(ULTRA, [CallOutcome(None, None, False, "timed out")], 0.92)
    assert metric.status == "failed" and not hard and metric.validation_errors == ["timed out"]
    assert (metric.input_tokens, metric.estimated_cost_usd, metric.time_to_first_token_ms) == (0, 0.0, None)


def test_aggregate_hard_failure_blocks_pass_even_with_high_mean():
    metric, hard = aggregate_metric(NANO, [ok(1.0), ok(0.95, hard=False)], 0.5)
    assert not hard and not metric.passes_validation


def test_case_is_vacuous():
    call = scan_repository(SAMPLE).calls[2]  # free-text node, no schema
    assert case_is_vacuous(call, BenchmarkCase(vars={}))
    assert not case_is_vacuous(call, BenchmarkCase(vars={}, must_include=["1."]))
    assert not case_is_vacuous(call, BenchmarkCase(vars={}, max_chars=10))
    assert not case_is_vacuous(call, BenchmarkCase(vars={}, expected="x"))
    structured = scan_repository(SAMPLE).calls[0]
    assert not case_is_vacuous(structured, BenchmarkCase(vars={}))


# ---------------------------------------------------------------- runner


def _run() -> BenchmarkRun:
    return BenchmarkRun(run_id="r", status="running", progress_pct=0, nodes=[], data_source="live",
                        created_at=datetime.now(timezone.utc).isoformat())


class ScriptedClient:
    """Answers by model: good JSON for big models, junk for small ones."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []
        self.active = 0
        self.max_active = 0

    async def complete(self, model, messages, params):
        self.calls.append((model, messages, params))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return self.behaviour(model, messages)
        finally:
            self.active -= 1


def fake_capture(root, call, cases, timeout):
    return [CaptureResult(CapturedRequest([{"role": "user", "content": f"{call.node_id}:{i}"}], {"max_tokens": 50}))
            for i, _ in enumerate(cases)]


def behaviour(model, messages):
    node = messages[0]["content"]
    if "Ultra" in model and "classify" in node:
        raise LLMError(f"{model}: HTTP 503: overloaded")
    if "classify" in node:
        category = ["billing", "tech_support", "general"][int(node.rsplit(":", 1)[1])]
        return comp(f'{{"category": "{category}", "confidence": 0.9}}' if "Nano" not in model else category)
    if "extract" in node:
        if node.endswith(":0"):
            return comp('{"account_id": "ACC-48213", "error_code": "SYNC-503"}')
        return comp('{"account_id": "77120"}')
    return comp("1. Restart the app and wait.\n2. Reinstall it, then open the project again." * 2)


async def _execute(client, calls, capture=fake_capture, root=SAMPLE):
    run = _run()
    extras = RunExtras(repo_root=root, node_ids=[c.node_id for c in calls], threshold=0.92)
    await BenchmarkRunner(S, client, capture=capture).run(run, extras, calls)
    return run, extras


async def test_runner_fills_matrix_and_recommendations():
    calls = scan_repository(SAMPLE).calls
    client = ScriptedClient(behaviour)
    run, extras = await _execute(client, calls)
    assert run.status == "complete" and run.progress_pct == 100
    assert run.current_step == "Completed 21 model evaluations across 3 nodes"
    assert len(client.calls) == 24  # 6 cases x 4 models
    assert client.max_active <= S.benchmark_concurrency
    by_node = {n.node_id: n for n in run.nodes}
    classify = by_node["node_classify_customer_intent"].metrics_by_model
    assert classify[NANO.id].passes_validation is False
    assert classify[ULTRA.id].status == "failed"
    assert by_node["node_classify_customer_intent"].recommended_model_id == LIGHT.id
    assert extras.hard_ok["node_classify_customer_intent"][NANO.id] is False
    assert by_node["node_extract_ticket_metadata"].recommended_model_id in (NANO.id, LIGHT.id)
    assert extras.spent_usd > 0


async def test_runner_isolates_unexpected_exceptions():
    def boom(model, messages):
        if "Super" in model:
            raise RuntimeError("bug")
        return behaviour(model, messages)

    run, _ = await _execute(ScriptedClient(boom), scan_repository(SAMPLE).calls)
    assert run.status == "complete"
    metric = run.nodes[1].metrics_by_model[SUPER.id]
    assert metric.status == "failed" and "unexpected error: RuntimeError" in metric.validation_errors[0]


async def test_runner_timeout(monkeypatch):
    import dataclasses

    slow_settings = dataclasses.replace(S, benchmark_timeout_seconds=1)

    class Slow:
        async def complete(self, model, messages, params):
            await asyncio.sleep(5)

    calls = scan_repository(SAMPLE).calls[:1]
    run = _run()
    extras = RunExtras(repo_root=SAMPLE, node_ids=[calls[0].node_id], threshold=0.92)
    await BenchmarkRunner(slow_settings, Slow(), capture=fake_capture).run(run, extras, calls)
    metric = run.nodes[0].metrics_by_model[NANO.id]
    assert metric.status == "failed" and "timed out after 1s" in metric.validation_errors[0]


async def test_nodes_without_cases_are_failed_not_invented(tmp_path):
    (tmp_path / "a.py").write_text("import openai\ndef f(client):\n    client.chat.completions.create(model='m', messages=[])\n")
    calls = scan_repository(tmp_path).calls
    client = ScriptedClient(behaviour)
    run, _ = await _execute(client, calls, root=tmp_path)
    assert client.calls == []
    assert run.status == "complete"
    for metric in run.nodes[0].metrics_by_model.values():
        assert metric.status == "failed" and metric.validation_errors == [NO_CASES_ERROR]
    assert run.nodes[0].recommended_model_id is None


async def test_vacuous_cases_are_never_sent(tmp_path):
    (tmp_path / "a.py").write_text("import openai\ndef f(client):\n    client.chat.completions.create(model='m', messages=[])\n")
    (tmp_path / "cascade_cases.yaml").write_text("node_f:\n  - vars: {}\n")
    client = ScriptedClient(behaviour)
    run, _ = await _execute(client, scan_repository(tmp_path).calls, root=tmp_path)
    assert client.calls == []
    assert run.nodes[0].metrics_by_model[NANO.id].validation_errors == [VACUOUS_CASE_ERROR]


async def test_invalid_cases_file_marks_run_error(tmp_path):
    (tmp_path / "a.py").write_text("import openai\ndef f(client):\n    client.chat.completions.create(model='m', messages=[])\n")
    (tmp_path / "cascade_cases.yaml").write_text("node_f: nope\n")
    run, _ = await _execute(ScriptedClient(behaviour), scan_repository(tmp_path).calls, root=tmp_path)
    assert run.status == "error" and run.current_step.startswith("Invalid cascade_cases.yaml")


async def test_capture_crash_marks_run_error():
    def broken_capture(*a):
        raise OSError("disk full")

    run, _ = await _execute(ScriptedClient(behaviour), scan_repository(SAMPLE).calls, capture=broken_capture)
    assert run.status == "error" and run.current_step == "Benchmark failed: disk full"


async def test_real_capture_integration():
    """Uses the real sandbox capture against the sample repo; the client is a test double."""
    calls = scan_repository(SAMPLE).calls[:1]
    seen = []

    class Recorder:
        async def complete(self, model, messages, params):
            seen.append(messages)
            return comp('{"category": "billing", "confidence": 0.9}')

    run = _run()
    extras = RunExtras(repo_root=SAMPLE, node_ids=[calls[0].node_id], threshold=0.92)
    await BenchmarkRunner(S, Recorder()).run(run, extras, calls)
    assert run.status == "complete"
    assert seen and seen[0][0]["content"].startswith("You are a support triage classifier")
