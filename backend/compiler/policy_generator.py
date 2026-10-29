"""Pure safe-YAML policy generation; no writes, inference or automatic application."""

from __future__ import annotations

import hashlib

from backend.schemas import OptimizationResult, RoutingPolicyArtifact, content_digest


def generate_policy(result: OptimizationResult) -> RoutingPolicyArtifact:
    result = OptimizationResult.model_validate(result)
    routes, omissions = [], []
    for decision in result.decisions:
        if decision.status not in ("recommended", "baseline_retained"):
            omissions.append({"node_id": decision.node_id, "status": decision.status, "reason": decision.reason})
            continue
        selected = next(item for item in decision.candidates if item.model.identifier == decision.selected_model_id)
        baseline = next(item for item in decision.candidates if item.model.identifier == decision.baseline_model_id)
        routes.append({
            "node_id": decision.node_id, "model": selected.model.model_dump(mode="json"),
            "provenance": decision.provenance, "decision_status": decision.status, "reason": decision.reason,
            "quality_threshold": format(decision.quality_threshold, "f"),
            "observed_case_pass_rate": format(selected.quality_pass_rate, "f"),
            "case_count": selected.planned_cases, "measurement_digest": selected.measurement_digest,
            "baseline_model": baseline.model.model_dump(mode="json"),
            "recorded_baseline_cost_usd": format(baseline.cost_total_usd, "f"),
            "recorded_selected_cost_usd": format(selected.cost_total_usd, "f"),
            "recorded_savings_usd": format(decision.recorded_savings_usd, "f"),
            "latency_ms": selected.latency_ms.model_dump(mode="json"),
        })
    if not routes:
        return RoutingPolicyArtifact(status="unavailable", reason="no_eligible_routes", route_count=0)
    try:
        import yaml
    except ImportError:
        return RoutingPolicyArtifact(status="unavailable", reason="serializer_unavailable", route_count=0)
    document = {
        "schema_version": "cascaderouter.policy.v1", "analysis_id": result.plan.analysis_id,
        "analysis_digest": result.plan.analysis_digest, "run_id": result.run_id,
        "benchmark_digest": result.benchmark_digest, "optimization_digest": content_digest(result),
        "objective_version": result.objective_version, "configuration_version": result.configuration_version,
        "configuration_digest": result.configuration_digest, "provenance": result.provenance,
        "approval_manifest_digest": result.approval_manifest_digest, "recording_dataset_digest": result.recording_dataset_digest,
        "case_set": result.plan.case_set.model_dump(mode="json"), "case_set_digest": result.plan.case_set_digest,
        "evaluation_profile": result.plan.evaluation_profile.model_dump(mode="json"),
        "evaluation_profile_digest": result.plan.evaluation_profile_digest,
        "registry_digest": result.plan.registry_digest, "execution_digest": result.plan.execution_digest,
        "decisions_complete": result.decisions_complete, "routes": routes, "omitted_nodes": omissions,
    }
    try:
        encoded = yaml.safe_dump(document, sort_keys=True, allow_unicode=False, default_flow_style=False, line_break="\n", width=120)
        class UniqueSafeLoader(yaml.SafeLoader):
            pass

        def mapping(loader, node):
            values = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                if type(key) is not str or key in values:
                    raise ValueError("Duplicate or invalid policy key.")
                values[key] = loader.construct_object(value_node)
            return values

        UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        # Only our own bounded generated YAML is loaded; no external YAML endpoint.
        if len(encoded.encode("utf-8")) > 524288:
            raise ValueError()
        loader = UniqueSafeLoader(encoded)
        try:
            if loader.get_single_data() != document:
                raise ValueError()
        finally:
            loader.dispose()
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        return RoutingPolicyArtifact(status="unavailable", reason="serialization_failed", route_count=0)
    return RoutingPolicyArtifact(
        status="available" if result.decisions_complete else "partial", route_count=len(routes), yaml_content=encoded,
        digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    )
