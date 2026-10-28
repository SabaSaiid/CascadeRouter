"""In-process synthetic adapters only. No fixture claims local inference provenance."""

import ast
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.compiler.policy_generator import generate_policy
from backend.compiler.router_optimizer import optimize
from backend.config import BackendConfig
from backend.runtime.cascade_router import CascadeRouter, ExecutorRegistration, RuntimeConfigurationError
from backend.schemas import (
    EvaluationProfile, LocalBenchmarkCase, OptimizationResponse, RuntimeAdapterSpec, RuntimeAuthorization,
    RuntimeResult, RuntimeRouteBinding, RuntimeValidationContract, ScanResponse, content_digest,
)


@pytest.fixture
def runtime_environment(optimization_environment):
    env = optimization_environment
    def build(*, primary=None, fallback=None, profile=None, output_kind="text", mode="expected_output", expected="PRIVATE_CAPTURE_ONE", **limits):
        cases = None if profile is None else [LocalBenchmarkCase(identifier="case-one", input_text="test-one", expected_output=expected),
                                              LocalBenchmarkCase(identifier="case-two", input_text="test-two", expected_output=expected)]
        sample = env.build_optimization(profile=profile, cases=cases)
        result = optimize(sample.snapshot)
        policy = OptimizationResponse(result=result, policy=generate_policy(result))
        node = result.decisions[0].node_id
        calls = []
        def default_primary(value, context):
            calls.append((context.adapter.adapter_id, value))
            return expected
        operations = [primary or default_primary] + ([] if fallback is None else [fallback])
        ids = ["primary"] + ([] if fallback is None else ["fallback"])
        models = [sample.job.plan.models[1]] + ([] if fallback is None else [sample.job.plan.models[0]])
        registrations = tuple(ExecutorRegistration(RuntimeAdapterSpec(
            adapter_id=adapter_id, model=model, capability="local_in_process", provenance="test",
            max_execution_seconds=1.0, supports_cancellation=False, output_kind=output_kind,
            evaluation_profile=sample.job.plan.evaluation_profile, evaluation_profile_digest=sample.job.plan.evaluation_profile_digest,
        ), operation) for adapter_id, model, operation in zip(ids, models, operations))
        binding = RuntimeRouteBinding(node_id=node, primary_adapter_id="primary", fallback_adapter_id=None if fallback is None else "fallback")
        authorization = RuntimeAuthorization(analysis_id=env.analysis.analysis_id, analysis_digest=sample.job.plan.analysis_digest,
            optimization_digest=content_digest(result), policy_digest=policy.policy.digest, bindings=[binding])
        contract = RuntimeValidationContract(profile=sample.registry.document.evaluation_profiles[0], output_kind=output_kind,
                                              mode=mode, expected_output=expected if mode == "expected_output" else None)
        settings = BackendConfig(**{"job_workers": 1, "runtime_timeout_seconds": 1.0, **limits})
        return SimpleNamespace(analysis=env.analysis, sample=sample, policy=policy, node=node, registrations=registrations,
                               authorization=authorization, contract=contract, settings=settings, calls=calls)
    return build


def router_for(env, **changes):
    return CascadeRouter(changes.pop("settings", env.settings), changes.pop("registrations", env.registrations),
                         authorization=changes.pop("authorization", env.authorization), mode=changes.pop("mode", "test"), **changes)


def run(router, env, **changes):
    return router.execute(changes.pop("node_id", env.node), changes.pop("analysis", env.analysis), changes.pop("policy", env.policy),
                          changes.pop("input_data", {"request": "PRIVATE_REQUEST"}), validation=changes.pop("validation", env.contract), **changes)


def test_registered_in_process_adapter_preserves_text_and_test_provenance(runtime_environment):
    env = runtime_environment()
    with router_for(env) as router:
        result = run(router, env)
        assert result.status == "succeeded" and result.result_data == "PRIVATE_CAPTURE_ONE"
        assert result.provenance == "test" and result.selected_model == env.registrations[0].spec.model
        assert result.attempt_count == 1 and result.validation_status == "passed" and not result.fallback_attempted
        assert env.calls == [("primary", {"request": "PRIVATE_REQUEST"})]
        assert result.attempts[0].evaluation.status == "passed"
        assert "PRIVATE_" not in result.model_dump_json(exclude={"result_data"}) and "PRIVATE_" not in repr(result)
        assert RuntimeResult.model_validate_json(result.model_dump_json()) == result


def test_no_registered_executor_is_controlled_unavailable(runtime_environment):
    env = runtime_environment()
    with router_for(env, registrations=()) as router:
        result = run(router, env)
    assert result.status == "unavailable" and result.reason == "adapter_unavailable"
    assert result.attempt_count == 0 and result.result_data is None and result.provenance is None and not env.calls


def test_test_executor_and_policy_never_satisfy_production_mode(runtime_environment):
    env = runtime_environment()
    with router_for(env, mode="local") as router:
        result = run(router, env)
    assert result.status == "unavailable" and result.reason == "provenance_forbidden"
    assert not env.calls and result.attempts == ()


def test_parsed_policy_without_separate_execution_permission_is_unavailable(runtime_environment):
    env = runtime_environment()
    with router_for(env, authorization=None) as router:
        result = run(router, env)
    assert result.reason == "authorization_missing" and result.attempt_count == 0 and not env.calls


def json_profile():
    return EvaluationProfile(identifier="profile", version="v1", criteria_id="test-runtime-schema", mechanism="json_schema",
        validation_schema_json='{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":false}')


def test_primary_schema_failure_uses_explicit_registered_fallback_and_preserves_shape(runtime_environment):
    calls = []
    def primary(value, context):
        calls.append(context.adapter.adapter_id)
        value["mutated"] = True
        return {"ok": "wrong-type"}
    def fallback(value, context):
        calls.append(context.adapter.adapter_id)
        assert "mutated" not in value
        return {"ok": True}
    env = runtime_environment(primary=primary, fallback=fallback, profile=json_profile(), output_kind="json_value", expected='{"ok":true}')
    original = {"request": ["private"]}
    with router_for(env) as router:
        result = run(router, env, input_data=original)
    assert result.status == "succeeded" and result.result_data == {"ok": True} and type(result.result_data) is dict
    assert original == {"request": ["private"]} and calls == ["primary", "fallback"]
    assert result.fallback_attempted and result.attempt_count == 2 and result.selected_adapter_id == "fallback"
    assert result.attempts[0].execution_status == "succeeded" and result.attempts[0].validation_status == "failed"
    assert result.attempts[1].validation_status == "passed"


@pytest.mark.parametrize("fallback", [False, True])
def test_validation_failure_never_returns_output_or_claims_success(runtime_environment, fallback):
    env = runtime_environment(primary=lambda *_: "wrong", fallback=(lambda *_: "also wrong") if fallback else None)
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "failed" and result.validation_status == "failed" and result.result_data is None
    assert result.attempt_count == (2 if fallback else 1) and result.fallback_attempted == fallback
    assert all(item.execution_status == "succeeded" and item.validation_status == "failed" for item in result.attempts)


def test_structural_validation_does_not_invent_semantic_quality_success(runtime_environment):
    env = runtime_environment(primary=lambda *_: {"ok": False}, profile=json_profile(), output_kind="json_value",
                              mode="structure", expected='{"ok":true}')
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "succeeded" and result.reason == "structure_validated" and result.result_data == {"ok": False}
    assert result.attempts[0].evaluation.status == "inconclusive"
    assert result.attempts[0].evaluation.reason == "ground_truth_unavailable"


@pytest.mark.parametrize("validation", [None, {"profile": {}}, {"arbitrary_validator": "never.import.this"}])
def test_missing_or_invalid_validation_is_inconclusive_before_execution(runtime_environment, validation):
    env = runtime_environment()
    with router_for(env) as router:
        result = run(router, env, validation=validation)
    assert result.status == "inconclusive" and result.reason == "validation_unavailable" and not env.calls


def test_validation_contract_cannot_change_profile_or_output_type(runtime_environment):
    env = runtime_environment()
    data = env.contract.model_dump()
    data["output_kind"] = "json_value"
    with router_for(env) as router:
        assert run(router, env, validation=data).reason == "validation_unavailable"
    assert not env.calls


def test_unknown_node_is_rejected_without_execution(runtime_environment):
    env = runtime_environment()
    with router_for(env) as router:
        result = run(router, env, node_id="llm_" + "0" * 24)
        with pytest.raises(RuntimeConfigurationError):
            run(router, env, node_id="../../private")
    assert result.reason == "unknown_node" and not env.calls


@pytest.mark.parametrize("field", ["primary_adapter_id", "fallback_adapter_id"])
def test_unregistered_primary_or_fallback_rejects_whole_binding(runtime_environment, field):
    env = runtime_environment(fallback=lambda *_: "PRIVATE_CAPTURE_ONE")
    data = env.authorization.model_dump()
    data["bindings"][0][field] = "unknown"
    with router_for(env, authorization=data) as router:
        result = run(router, env)
    assert result.reason == "adapter_unavailable" and not env.calls and result.attempt_count == 0


def test_wrong_model_or_version_in_registry_is_rejected(runtime_environment):
    env = runtime_environment()
    original = env.registrations[0]
    spec = RuntimeAdapterSpec.model_validate({**original.spec.model_dump(), "model": {"identifier": "unknown/model", "version": "v1"}})
    with router_for(env, registrations=(replace(original, spec=spec),)) as router:
        assert run(router, env).reason == "policy_invalid"
    assert not env.calls


def test_repeated_model_and_cyclic_or_duplicate_bindings_are_rejected(runtime_environment):
    env = runtime_environment(fallback=lambda *_: "PRIVATE_CAPTURE_ONE")
    first, second = env.registrations
    repeated = replace(second, spec=RuntimeAdapterSpec.model_validate({**second.spec.model_dump(), "model": first.spec.model}))
    with router_for(env, registrations=(first, repeated)) as router:
        assert run(router, env).reason == "policy_invalid"
    data = env.authorization.model_dump(mode="json")
    data["bindings"] *= 2
    with pytest.raises(RuntimeConfigurationError):
        router_for(env, authorization=data)
    with pytest.raises(ValidationError):
        RuntimeRouteBinding(node_id=env.node, primary_adapter_id="same", fallback_adapter_id="same")
    assert not env.calls


def test_configured_attempt_limit_rejects_fallback_before_primary_runs(runtime_environment):
    env = runtime_environment(fallback=lambda *_: "PRIVATE_CAPTURE_ONE", runtime_max_attempts=1)
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "unavailable" and result.reason == "policy_invalid" and not env.calls


@pytest.mark.parametrize("kind", ["input", "output"])
def test_input_and_output_byte_limits_cannot_be_bypassed(runtime_environment, kind):
    env = runtime_environment(max_request_body_bytes=32) if kind == "input" else runtime_environment(primary=lambda *_: "x" * 20000)
    with router_for(env) as router:
        result = run(router, env, input_data="x" * 40 if kind == "input" else "test")
    assert result.result_data is None and result.reason == kind + "_limit"
    assert result.attempt_count == (0 if kind == "input" else 1)


@pytest.mark.parametrize("kind", ["cycle", "object", "nonfinite", "nonstring_key", "deep"])
def test_unsafe_or_over_budget_input_is_rejected(runtime_environment, kind):
    value = []
    if kind == "cycle":
        value.append(value)
    elif kind == "object":
        value = object()
    elif kind == "nonfinite":
        value = float("nan")
    elif kind == "nonstring_key":
        value = {1: "not-string-key"}
    else:
        for _ in range(18):
            value = [value]
    env = runtime_environment()
    with router_for(env) as router:
        result = run(router, env, input_data=value)
    assert result.status == "unavailable" and result.reason in ("input_invalid", "input_limit") and not env.calls


def test_timeout_preserves_capacity_until_blocking_work_really_finishes(runtime_environment):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    contexts = []
    def blocking(_value, context):
        contexts.append(context)
        entered.set()
        try:
            assert release.wait(5)
            return "PRIVATE_CAPTURE_ONE"
        finally:
            finished.set()
    env = runtime_environment(primary=blocking)
    spec = RuntimeAdapterSpec.model_validate({**env.registrations[0].spec.model_dump(), "max_execution_seconds": 0.03})
    with router_for(env, registrations=(replace(env.registrations[0], spec=spec),)) as router:
        try:
            result = run(router, env)
            assert entered.is_set() and result.status == "timed_out" and result.worker_still_running
            assert result.attempt_count == 1 and result.attempts[0].execution_status == "running"
            assert result.result_data is None and contexts[0].cancelled() and not finished.is_set()
            assert run(router, env).reason == "capacity_exceeded"
        finally:
            release.set()
        assert finished.wait(5)


def test_cancellation_never_claims_thread_termination_or_attempts_fallback(runtime_environment):
    entered, release, cancellation = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def blocking(*_):
        entered.set()
        assert release.wait(5)
        return "wrong"
    env = runtime_environment(primary=blocking, fallback=lambda *_: calls.append("fallback"))
    with router_for(env) as router:
        with ThreadPoolExecutor(max_workers=1) as host:
            request = host.submit(run, router, env, cancellation=cancellation)
            try:
                assert entered.wait(5)
                cancellation.set()
                result = request.result(timeout=5)
                assert result.status == "cancelled" and result.worker_still_running and result.attempt_count == 1
                assert not result.fallback_attempted and result.result_data is None
            finally:
                release.set()
    assert not calls


def test_already_cancelled_request_does_not_call_an_adapter(runtime_environment):
    env = runtime_environment()
    cancellation = threading.Event()
    cancellation.set()
    with router_for(env) as router:
        result = run(router, env, cancellation=cancellation)
    assert result.status == "cancelled" and result.attempt_count == 0 and not env.calls


@pytest.mark.parametrize("error", [RuntimeError, SystemExit, KeyboardInterrupt])
def test_arbitrary_adapter_exceptions_are_sanitized_without_retry(runtime_environment, error):
    calls = []
    def failed(*_):
        raise error("PRIVATE_INTERNAL_EXCEPTION")
    env = runtime_environment(primary=failed, fallback=lambda *_: calls.append("fallback"))
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "failed" and result.reason == "adapter_failed" and result.result_data is None
    assert result.attempts[0].execution_status == "failed" and result.attempt_count == 1 and not calls
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("change", ["yaml_duplicate", "wrong_threshold", "wrong_authorization", "source_identity", "unknown_field"])
def test_policy_or_authorization_forgery_is_rejected_before_execution(runtime_environment, change):
    env = runtime_environment()
    policy, analysis, authorization = env.policy.model_dump(), env.analysis, env.authorization
    if change == "yaml_duplicate":
        text = policy["policy"]["yaml_content"] + "provenance: test\n"
        policy["policy"].update(yaml_content=text, digest=hashlib.sha256(text.encode()).hexdigest())
    elif change == "wrong_threshold":
        policy["result"]["quality_threshold"] = "1.1"
    elif change == "wrong_authorization":
        authorization = RuntimeAuthorization.model_validate({**authorization.model_dump(), "policy_digest": "0" * 64})
    elif change == "source_identity":
        analysis = ScanResponse.model_validate({**analysis.model_dump(), "timestamp": "2020-01-01T00:00:00Z"})
    else:
        policy["result"]["command"] = "never executed"
    with router_for(env, authorization=authorization) as router:
        result = run(router, env, policy=policy, analysis=analysis)
    assert result.reason == "policy_invalid" and result.attempt_count == 0 and not env.calls


def test_trace_is_deterministic_and_never_adds_metrics(runtime_environment):
    env = runtime_environment()
    with router_for(env) as router:
        first, second = run(router, env), run(router, env)
    assert first.model_dump_json() == second.model_dump_json()
    assert not {"latency", "tokens", "cost", "quality_score", "savings"} & first.model_dump().keys()


def test_request_results_and_adapter_inputs_do_not_share_mutable_objects(runtime_environment):
    shared = {"ok": True}
    env = runtime_environment(primary=lambda *_: shared, profile=json_profile(), output_kind="json_value", expected='{"ok":true}')
    with router_for(env) as router:
        first, second = run(router, env), run(router, env)
        first.result_data["ok"] = False
    assert second.result_data == shared == {"ok": True}


def test_no_network_file_reads_or_writes_during_routing(runtime_environment, monkeypatch):
    import builtins
    import socket
    env = runtime_environment()
    def forbidden(*_args, **_kwargs):
        pytest.fail("Runtime must not access files or network.")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    with router_for(env) as router:
        assert run(router, env).status == "succeeded"


def test_runtime_source_has_no_dynamic_execution_provider_import_or_network_dependency():
    path = Path(__file__).parents[2] / "backend" / "runtime" / "cascade_router.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))
    forbidden = {"openai", "nebius", "tavily", "requests", "httpx", "socket", "urllib", "subprocess", "importlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in forbidden for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec", "__import__", "open"}


def test_invalid_and_duplicate_callable_registrations_are_rejected(runtime_environment):
    env = runtime_environment()
    for registrations in ((env.registrations[0],) * 2, (replace(env.registrations[0], operation="arbitrary.import"),)):
        with pytest.raises(RuntimeConfigurationError):
            router_for(env, registrations=registrations)
    async def asynchronous(*_):
        return "never awaited"
    with pytest.raises(RuntimeConfigurationError):
        router_for(env, registrations=(replace(env.registrations[0], operation=asynchronous),))


def test_closed_router_cannot_admit_more_work(runtime_environment):
    env = runtime_environment()
    router = router_for(env)
    router.close()
    assert run(router, env).reason == "closed" and not env.calls


@pytest.mark.parametrize("value", [{"ok": True}, [1, "two"], None, False, 3, "ordinary string"])
def test_json_value_success_preserves_original_application_type(runtime_environment, value):
    profile = EvaluationProfile(identifier="profile", version="v1", criteria_id="test-json", mechanism="json")
    env = runtime_environment(primary=lambda *_: value, profile=profile, output_kind="json_value", expected=json.dumps(value))
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "succeeded" and result.result_data == value and type(result.result_data) is type(value)


def test_validation_work_is_within_the_same_timeout_and_capacity_boundary(runtime_environment, monkeypatch):
    from backend.runtime import cascade_router
    entered, release = threading.Event(), threading.Event()
    original = cascade_router.evaluate
    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    env = runtime_environment(runtime_timeout_seconds=0.08)
    monkeypatch.setattr(cascade_router, "evaluate", blocked)
    with router_for(env) as router:
        try:
            result = run(router, env)
            assert entered.is_set() and result.status == "timed_out" and result.worker_still_running
            assert result.attempts[0].execution_status == "succeeded" and result.attempts[0].validation_status == "not_run"
            assert result.result_data is None and run(router, env).reason == "capacity_exceeded"
        finally:
            release.set()


def test_per_adapter_serialization_has_no_waiting_backlog(runtime_environment):
    entered, release = threading.Event(), threading.Event()
    def blocked(*_):
        entered.set()
        assert release.wait(5)
        return "PRIVATE_CAPTURE_ONE"
    env = runtime_environment(primary=blocked, job_workers=2)
    with router_for(env) as router:
        with ThreadPoolExecutor(max_workers=1) as host:
            first = host.submit(run, router, env)
            try:
                assert entered.wait(5)
                second = run(router, env)
                assert second.reason == "capacity_exceeded" and second.attempt_count == 0
            finally:
                release.set()
            assert first.result(timeout=5).status == "succeeded"


def test_fallback_keeps_original_request_deadline(runtime_environment):
    deadlines = []
    def primary(_value, context):
        deadlines.append(context.deadline)
        return "wrong"
    def fallback(_value, context):
        deadlines.append(context.deadline)
        return "PRIVATE_CAPTURE_ONE"
    env = runtime_environment(primary=primary, fallback=fallback)
    with router_for(env) as router:
        assert run(router, env).status == "succeeded"
    assert len(deadlines) == 2 and deadlines[0] == deadlines[1]


@pytest.mark.parametrize("field,value", [("runtime_max_attempts", 0), ("runtime_max_attempts", 3), ("runtime_max_attempts", True),
                                        ("runtime_timeout_seconds", 0), ("runtime_timeout_seconds", float("inf"))])
def test_runtime_configuration_limits_are_strict(field, value):
    with pytest.raises(ValidationError):
        BackendConfig(**{field: value})


def test_shutdown_waits_for_real_work_and_does_not_claim_termination(runtime_environment):
    entered, release = threading.Event(), threading.Event()
    def blocked(*_):
        entered.set()
        assert release.wait(5)
        return "PRIVATE_CAPTURE_ONE"
    env = runtime_environment(primary=blocked)
    router = router_for(env)
    with ThreadPoolExecutor(max_workers=2) as host:
        request = host.submit(run, router, env)
        try:
            assert entered.wait(5)
            closing = host.submit(router.close)
            result = request.result(timeout=5)
            assert result.status == "unavailable" and result.reason == "closed" and result.worker_still_running
            assert not closing.done() and result.result_data is None
        finally:
            release.set()
        closing.result(timeout=5)
    assert run(router, env).reason == "closed"


def test_output_objects_cannot_invoke_custom_iteration_or_serialization(runtime_environment):
    class Opaque:
        def __iter__(self):
            pytest.fail("Opaque output must not be iterated.")
        def __repr__(self):
            pytest.fail("Opaque output must not be rendered.")
    env = runtime_environment(primary=lambda *_: Opaque())
    with router_for(env) as router:
        result = run(router, env)
    assert result.status == "failed" and result.reason == "output_invalid" and result.result_data is None


def test_container_and_escaped_unicode_input_limits_are_enforced(runtime_environment):
    env = runtime_environment(max_request_body_bytes=128)
    with router_for(env) as router:
        assert run(router, env, input_data=[0] * 4097).reason == "input_limit"
        assert run(router, env, input_data="\U0001f600" * 11).reason == "input_limit"
    assert not env.calls


def test_partial_policy_never_executes_an_omitted_node(runtime_environment):
    from backend.schemas import OptimizationResult, RoutingDecision
    env = runtime_environment()
    original = env.policy.result
    omitted_node = next(node.node_id for node in env.analysis.nodes if node.node_id != env.node)
    unresolved = RoutingDecision(analysis_id=env.analysis.analysis_id, node_id=omitted_node, provenance="test",
        status="inconclusive", reason="baseline_ineligible", baseline_model_id=original.plan.models[0].identifier,
        quality_threshold=original.quality_threshold, candidates=())
    data = original.model_dump()
    data["plan"]["node_ids"] = (*original.plan.node_ids, omitted_node)
    data.update(decisions=sorted([*original.decisions, unresolved], key=lambda item: item.node_id), nodes_considered=2,
                nodes_inconclusive=1, status="inconclusive", decisions_complete=False)
    result = OptimizationResult.model_validate(data)
    assert result.provenance == "test"
    policy = OptimizationResponse(result=result, policy=generate_policy(result))
    authorization = RuntimeAuthorization.model_validate({**env.authorization.model_dump(), "optimization_digest": content_digest(result),
                                                        "policy_digest": policy.policy.digest})
    with router_for(env, authorization=authorization) as router:
        assert run(router, env, policy=policy).status == "succeeded"
        response = run(router, env, policy=policy, node_id=omitted_node)
    assert response.reason == "unknown_node" and response.attempt_count == 0 and len(env.calls) == 1


def test_runtime_schema_cannot_relabel_a_failed_evaluation_as_success(runtime_environment):
    env = runtime_environment()
    with router_for(env) as router:
        result = run(router, env)
    data = result.model_dump()
    # A JSON comparison can fail even when structural validation passed. That
    # must not be accepted as a successful expected-output runtime evaluation.
    data["attempts"][0]["evaluation"].update(status="failed", reason="mismatch", validation_status="passed")
    with pytest.raises(ValidationError):
        RuntimeResult.model_validate(data)


@pytest.mark.parametrize("interrupt", ["cancel", "timeout"])
def test_interruption_during_input_copy_never_invokes_adapter_after_wait_returns(runtime_environment, monkeypatch, interrupt):
    from backend.runtime import cascade_router
    entered, release, cancellation = threading.Event(), threading.Event(), threading.Event()
    env = runtime_environment(runtime_timeout_seconds=0.1 if interrupt == "timeout" else 1.0)
    original = cascade_router.json.loads
    def blocked(data, *args, **kwargs):
        if threading.current_thread().name.startswith("cascade-local"):
            entered.set()
            assert release.wait(5)
        return original(data, *args, **kwargs)
    monkeypatch.setattr(cascade_router.json, "loads", blocked)
    with router_for(env) as router:
        with ThreadPoolExecutor(max_workers=1) as host:
            request = host.submit(run, router, env, cancellation=cancellation)
            try:
                assert entered.wait(5)
                if interrupt == "cancel":
                    cancellation.set()
                result = request.result(timeout=5)
                assert result.status == ("cancelled" if interrupt == "cancel" else "timed_out")
                assert result.attempt_count == 0 and result.worker_still_running and not env.calls
            finally:
                release.set()
    assert not env.calls
