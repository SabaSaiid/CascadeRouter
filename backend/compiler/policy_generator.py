"""Generate the declarative routing policy (`.cascaderouter.yaml`).

The same document is read back by `backend/runtime/cascade_router.py`.
Emitted with `yaml.safe_dump` and verified by a strict round-trip load
(duplicate keys rejected) before it is returned.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import yaml

from backend.compiler.router_optimizer import NodeDecision

POLICY_FILENAME = ".cascaderouter.yaml"
POLICY_VERSION = "1.0"
DEFAULT_MAX_RETRIES = 1


class PolicyError(ValueError):
    """The generated policy failed its round-trip verification."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PolicyError(f"duplicate key {key!r} in policy")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_policy_text(text: str) -> dict[str, Any]:
    data = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    if not isinstance(data, dict):
        raise PolicyError("policy must be a mapping")
    return data


def node_rule(
    decision: NodeDecision, expected_schema: Optional[dict[str, Any]], json_required: bool
) -> dict[str, Any]:
    """Routing rule for one node, as stored under `nodes.<node_id>`."""
    return {
        "status": decision.status,
        "primary_model": decision.recommended_model,
        "fallback_model": decision.fallback_model,
        "baseline_model": decision.baseline_model,
        "routing_conditions": {
            "min_quality_score": None,  # filled by build_policy (threshold is global)
            "enforce_json": bool(json_required),
            "required_fields": list((expected_schema or {}).get("required", [])),
            "max_retries": DEFAULT_MAX_RETRIES,
        },
        "evidence": {
            "baseline_cost_usd": decision.baseline_cost_usd,
            "optimized_cost_usd": decision.optimized_cost_usd,
            "cost_reduction_pct": decision.cost_reduction_pct,
            "baseline_latency_ms": decision.baseline_latency_ms,
            "optimized_latency_ms": decision.optimized_latency_ms,
            "latency_reduction_pct": decision.latency_reduction_pct,
            "quality_score": decision.quality_score,
            "reason": decision.reason,
        },
    }


def build_policy(
    decisions: Iterable[tuple[NodeDecision, Optional[dict[str, Any]], bool]],
    *,
    threshold: float,
    repository: str,
    run_id: str,
    data_source: str,
    total_cost_reduction_pct: Optional[float],
    generated_at: Optional[datetime] = None,
) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for decision, schema, json_required in decisions:
        rule = node_rule(decision, schema, json_required)
        rule["routing_conditions"]["min_quality_score"] = threshold
        nodes[decision.node_id] = rule
    return {
        "version": POLICY_VERSION,
        "generated_by": "CascadeRouter FinOps Compiler",
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "repository": repository,
        "benchmark_run_id": run_id,
        "data_source": data_source,
        "quality_threshold": threshold,
        "total_projected_cost_reduction_pct": total_cost_reduction_pct,
        "nodes": nodes,
    }


def dump_policy(policy: dict[str, Any]) -> str:
    """Serialise and verify: the text must load back to exactly `policy`."""
    text = yaml.safe_dump(policy, sort_keys=False, allow_unicode=True, default_flow_style=False)
    if load_policy_text(text) != policy:
        raise PolicyError("policy did not survive a YAML round-trip")
    return text


def dump_node_policy(node_id: str, rule: dict[str, Any]) -> str:
    return dump_policy({"node_id": node_id, **rule})
