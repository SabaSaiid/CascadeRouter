from datetime import datetime, timezone

import pytest
import yaml

from backend.compiler.policy_generator import (
    POLICY_VERSION,
    PolicyError,
    build_policy,
    dump_node_policy,
    dump_policy,
    load_policy_text,
)
from backend.compiler.router_optimizer import NodeDecision
from backend.runtime.cascade_router import CascadeRouter


def decision(node_id="node_a", status="optimized", rec="small", fb="big"):
    return NodeDecision(
        node_id=node_id, baseline_model="big", recommended_model=rec, fallback_model=fb,
        baseline_cost_usd=0.002, optimized_cost_usd=0.0001, cost_reduction_pct=95.0,
        baseline_latency_ms=1000.0, optimized_latency_ms=100.0, latency_reduction_pct=90.0,
        quality_score=0.97, status=status, reason="cheapest passing",
    )


def policy(**over):
    args = dict(threshold=0.92, repository="tests/fixtures/sample_repo", run_id="run_1", data_source="live",
                total_cost_reduction_pct=95.0, generated_at=datetime(2026, 10, 29, tzinfo=timezone.utc))
    args.update(over)
    return build_policy(
        [(decision(), {"required": ["category", "confidence"]}, True),
         (decision("node_b", status="baseline_retained", rec="big"), None, False)],
        **args,
    )


def test_build_policy_shape():
    p = policy()
    assert p["version"] == POLICY_VERSION and p["quality_threshold"] == 0.92
    assert p["generated_at"] == "2026-10-29T00:00:00+00:00"
    a = p["nodes"]["node_a"]
    assert a["primary_model"] == "small" and a["fallback_model"] == "big" and a["status"] == "optimized"
    assert a["routing_conditions"] == {"min_quality_score": 0.92, "enforce_json": True,
                                       "required_fields": ["category", "confidence"], "max_retries": 1}
    assert a["evidence"]["cost_reduction_pct"] == 95.0
    assert p["nodes"]["node_b"]["routing_conditions"]["required_fields"] == []


def test_dump_round_trips_and_keeps_order():
    text = dump_policy(policy())
    assert text.startswith("version: '1.0'\n")
    assert load_policy_text(text) == policy()
    assert yaml.safe_load(text) == policy()


def test_undefined_total_is_null_not_zero():
    assert load_policy_text(dump_policy(policy(total_cost_reduction_pct=None)))["total_projected_cost_reduction_pct"] is None


def test_runtime_reads_generated_policy():
    router = CascadeRouter.from_dict(load_policy_text(dump_policy(policy())))
    rule = router.rules["node_a"]
    assert (rule.primary_model, rule.fallback_model, rule.enforce_json) == ("small", "big", True)
    assert rule.required_fields == ("category", "confidence") and rule.max_retries == 1


def test_node_policy_snippet():
    p = policy()
    text = dump_node_policy("node_a", p["nodes"]["node_a"])
    assert text.startswith("node_id: node_a\n")
    assert load_policy_text(text)["primary_model"] == "small"


def test_duplicate_keys_rejected():
    with pytest.raises(PolicyError, match="duplicate key"):
        load_policy_text("a: 1\na: 2\n")


@pytest.mark.parametrize("text", ["- a\n- b\n", "just text", ""])
def test_non_mapping_rejected(text):
    with pytest.raises(PolicyError):
        load_policy_text(text)


def test_unsafe_yaml_tags_rejected():
    with pytest.raises(yaml.YAMLError):
        load_policy_text("a: !!python/object/apply:os.system ['echo hi']\n")


def test_dump_detects_non_round_trippable_values():
    with pytest.raises((PolicyError, yaml.YAMLError)):
        dump_policy({"x": float("nan")})
