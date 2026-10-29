import pytest

from backend.compiler.router_optimizer import decide_node, is_candidate, select_model
from backend.config import load_settings
from backend.schemas import BenchmarkMetric, LLMNode, NodeBenchmarkResult

S = load_settings()
NANO, LIGHT, SUPER, ULTRA = (m.id for m in S.models)
TIERS = {NANO: "efficient", LIGHT: "efficient", SUPER: "balanced", ULTRA: "powerful"}


def m(model_id, cost, latency=100.0, quality=1.0, passes=True, status="completed", tier=None):
    return BenchmarkMetric(
        model_id=model_id, model_name=model_id.split("/")[-1], tier=tier or TIERS.get(model_id, "efficient"),
        input_tokens=10, output_tokens=10, total_latency_ms=latency, estimated_cost_usd=cost,
        quality_score=quality, passes_validation=passes, is_estimated=False, status=status,
    )


def node(current=ULTRA):
    return LLMNode(node_id="n", file_path="a.py", line_number=1, current_model=current, call_signature="c()")


def matrix(*metrics):
    return {x.model_id: x for x in metrics}


def test_is_candidate():
    assert is_candidate(m("a", 1), 0.9, None)
    assert not is_candidate(m("a", 1, quality=0.8), 0.9, None)
    assert not is_candidate(m("a", 1, passes=False), 0.9, None)
    assert is_candidate(m("a", 1, passes=False, quality=0.95), 0.9, True)  # hard_ok overrides
    assert not is_candidate(m("a", 1, status="failed"), 0.0, True)


def test_select_cheapest_passing():
    ms = matrix(m("a", 3.0), m("b", 1.0, quality=0.5), m("c", 2.0))
    assert select_model(ms, 0.92) == "c"
    assert select_model(matrix(m("a", 1, passes=False)), 0.92) is None
    assert select_model({}, 0.92) is None


def test_near_tie_prefers_latency_within_2pct_of_cheapest():
    ms = matrix(m("a", 1.00, latency=300), m("b", 1.019, latency=200), m("c", 1.038, latency=100))
    # c is 3.8% above the cheapest, outside the window, even though it is within 2% of b.
    assert select_model(ms, 0.9) == "b"
    assert select_model(matrix(m("a", 1.0, latency=300), m("b", 1.03, latency=1)), 0.9) == "a"


def test_equal_cost_tie_breaks_on_latency_then_id():
    assert select_model(matrix(m("b", 1.0, latency=50), m("a", 1.0, latency=60)), 0.9) == "b"
    assert select_model(matrix(m("b", 1.0), m("a", 1.0)), 0.9) == "a"
    assert select_model(matrix(m("z", 0.0, latency=9), m("y", 0.0, latency=5)), 0.9) == "y"


def test_hard_ok_mapping():
    ms = matrix(m("a", 1.0, quality=0.95, passes=False), m("b", 2.0))
    assert select_model(ms, 0.9, {"a": True, "b": True}) == "a"
    assert select_model(ms, 0.9, {"a": False, "b": True}) == "b"
    assert select_model(ms, 0.9, {}) is None


def full(**over):
    base = {NANO: m(NANO, 0.1, 100), LIGHT: m(LIGHT, 0.1, 80), SUPER: m(SUPER, 0.5, 300), ULTRA: m(ULTRA, 2.0, 1000)}
    base.update(over)
    return NodeBenchmarkResult(node_id="n", metrics_by_model=base)


def test_decide_optimized():
    d = decide_node(node(), full(), 0.92, S)
    assert d.status == "optimized" and d.recommended_model == LIGHT  # cost tie, faster
    assert d.baseline_model == ULTRA and d.fallback_model == SUPER
    assert d.cost_reduction_pct == pytest.approx(95.0)
    assert d.latency_reduction_pct == pytest.approx(92.0)
    assert d.quality_score == 1.0


def test_decide_baseline_retained_when_nothing_cheaper_passes():
    r = full(**{NANO: m(NANO, 0.1, quality=0.5, passes=False), LIGHT: m(LIGHT, 0.1, quality=0.5, passes=False),
                SUPER: m(SUPER, 0.5, quality=0.5, passes=False)})
    d = decide_node(node(), r, 0.92, S)
    assert d.status == "baseline_retained" and d.recommended_model == ULTRA
    assert d.cost_reduction_pct == 0 and d.optimized_cost_usd == d.baseline_cost_usd


def test_decide_inconclusive_when_baseline_failed_or_most_failed():
    d = decide_node(node(), full(**{ULTRA: m(ULTRA, 0, status="failed", passes=False)}), 0.92, S)
    assert d.status == "inconclusive" and d.baseline_cost_usd == 0
    r = full(**{NANO: m(NANO, 0, status="failed"), LIGHT: m(LIGHT, 0, status="failed"), SUPER: m(SUPER, 0, status="failed")})
    assert decide_node(node(), r, 0.92, S).status == "inconclusive"


def test_unknown_baseline_falls_back_to_powerful_tier():
    d = decide_node(node(current="<dynamic>"), full(), 0.92, S)
    assert d.baseline_model == ULTRA and d.status == "optimized"


def test_fallback_escalates_and_only_self_when_already_top_tier():
    # Ultra chosen against a pricier non-catalog baseline: nothing is above Ultra,
    # so "fallback" is Ultra itself (the runtime then simply does not escalate).
    r = NodeBenchmarkResult(node_id="n", metrics_by_model={
        "acme/huge": m("acme/huge", 10.0, tier="powerful"), ULTRA: m(ULTRA, 2.0)})
    d = decide_node(node(current="acme/huge"), r, 0.92, S)
    assert d.recommended_model == ULTRA and d.fallback_model == ULTRA
    r2 = NodeBenchmarkResult(node_id="n", metrics_by_model={
        "acme/huge": m("acme/huge", 10.0, tier="powerful"), SUPER: m(SUPER, 1.0), ULTRA: m(ULTRA, 2.0)})
    d2 = decide_node(node(current="acme/huge"), r2, 0.92, S)
    assert d2.recommended_model == SUPER and d2.fallback_model == ULTRA


def test_threshold_is_respected():
    r = full(**{NANO: m(NANO, 0.1, quality=0.93), LIGHT: m(LIGHT, 0.1, quality=0.93)})
    assert decide_node(node(), r, 0.92, S).recommended_model in (NANO, LIGHT)
    assert decide_node(node(), r, 0.95, S).recommended_model == SUPER
