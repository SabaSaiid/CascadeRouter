"""Safe deterministic artifacts; synthetic policies stay explicitly test-labelled."""

import builtins
import hashlib

import pytest
import yaml
from pydantic import ValidationError

from backend.compiler.policy_generator import generate_policy
from backend.compiler.router_optimizer import optimize
from backend.schemas import OptimizationResult


def test_policy_safe_round_trip_determinism_and_no_file_writes(optimization_environment, monkeypatch):
    env = optimization_environment
    result = optimize(env.build_optimization().snapshot)
    before = set(env.repository.iterdir())
    def no_open(*args, **kwargs):
        pytest.fail("Pure policy generation must not open files.")
    monkeypatch.setattr(builtins, "open", no_open)
    artifact = generate_policy(result)
    assert artifact.status == "available" and artifact.route_count == 1
    assert artifact == generate_policy(result)
    assert hashlib.sha256(artifact.yaml_content.encode()).hexdigest() == artifact.digest
    data = yaml.safe_load(artifact.yaml_content)
    assert data["schema_version"] == "cascaderouter.policy.v1" and data["provenance"] == "test"
    assert data["routes"][0]["model"]["identifier"] == "local/candidate"
    assert "fallback" not in artifact.yaml_content and "regression" not in artifact.yaml_content
    assert "PRIVATE_" not in artifact.yaml_content and set(env.repository.iterdir()) == before


def test_inconclusive_nodes_emit_no_policy_routes(optimization_environment):
    result = optimize(optimization_environment.build_optimization(rates={"local/baseline": None, "local/candidate": "0.5"}).snapshot)
    artifact = generate_policy(result)
    assert artifact.status == "unavailable" and artifact.reason == "no_eligible_routes"
    assert artifact.yaml_content is None and artifact.route_count == 0


@pytest.mark.parametrize("field,value", [("node_id", "../../bad"), ("selected_model_id", "model\nroutes: forged"), ("selected_model_id", "unknown")])
def test_unsafe_or_unplanned_identifiers_are_rejected(optimization_environment, field, value):
    data = optimize(optimization_environment.build_optimization().snapshot).model_dump()
    data["decisions"][0][field] = value
    with pytest.raises(ValidationError):
        generate_policy(data)


def test_duplicate_node_assignments_and_versions_are_rejected(optimization_environment):
    data = optimize(optimization_environment.build_optimization().snapshot).model_dump(mode="json")
    data["decisions"] *= 2
    with pytest.raises(ValidationError):
        OptimizationResult.model_validate(data)


@pytest.mark.parametrize("change", ["invented_exclusion", "false_eligibility", "wrong_coverage", "wrong_threshold"])
def test_policy_validation_rejects_forged_eligibility_or_evidence_counts(optimization_environment, change):
    data = optimize(optimization_environment.build_optimization().snapshot).model_dump()
    candidate = data["decisions"][0]["candidates"][1]
    if change == "invented_exclusion":
        candidate.update(eligibility="rejected", reasons=("quality_failed",))
    elif change == "false_eligibility":
        candidate.update(cost_total_usd=None)
    elif change == "wrong_coverage":
        candidate.update(planned_cases=3, passed_cases=3)
    else:
        candidate.update(reasons=("threshold_not_met",))
    with pytest.raises(ValidationError):
        generate_policy(data)


def test_duplicate_yaml_keys_and_unsafe_tags_fail_round_trip(optimization_environment, monkeypatch):
    result = optimize(optimization_environment.build_optimization().snapshot)
    original = yaml.safe_dump
    for suffix in ("provenance: test\n", "evil: !!python/object/apply:os.system ['never-run']\n"):
        monkeypatch.setattr(yaml, "safe_dump", lambda *args, **kwargs: original(*args, **kwargs) + suffix)
        artifact = generate_policy(result)
        assert artifact.status == "unavailable" and artifact.reason == "serialization_failed"


def test_missing_serializer_is_a_controlled_capability_blocker(optimization_environment, monkeypatch):
    result = optimize(optimization_environment.build_optimization().snapshot)
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("test missing serializer")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    artifact = generate_policy(result)
    assert artifact.status == "unavailable" and artifact.reason == "serializer_unavailable"


def test_partial_policy_reports_omissions_without_inventing_a_route(optimization_environment):
    # A synthetic two-node decision fixture. It remains test provenance and is
    # never supplied to the production optimization service.
    env = optimization_environment
    successful = optimize(env.build_optimization().snapshot)
    missing = optimize(env.build_optimization(rates={"local/baseline": None, "local/candidate": "0.5"}).snapshot)
    data = successful.model_dump()
    second_id = env.analysis.nodes[1].node_id
    second = missing.decisions[0].model_dump()
    second["node_id"] = second_id
    data["plan"]["node_ids"] = (*successful.plan.node_ids, second_id)
    data["decisions"] = sorted([successful.decisions[0].model_dump(), second], key=lambda item: item["node_id"])
    data.update(nodes_considered=2, nodes_eligible=2, nodes_inconclusive=1, decisions_complete=False, status="inconclusive")
    partial = OptimizationResult.model_validate(data)
    artifact = generate_policy(partial)
    parsed = yaml.safe_load(artifact.yaml_content)
    assert artifact.status == "partial" and artifact.route_count == 1
    assert not parsed["decisions_complete"] and len(parsed["omitted_nodes"]) == 1
    assert parsed["omitted_nodes"][0]["node_id"] == second_id
    assert parsed["routes"][0]["node_id"] != second_id
