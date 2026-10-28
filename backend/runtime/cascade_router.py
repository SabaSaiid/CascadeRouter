"""Explicit trusted-host runtime; no discovery, files, inference or provider SDKs.

Blocking adapters run in a fixed pool with zero backlog admission. Timeouts stop
waiting and request cooperative cancellation; they never claim to kill a thread.
The slot stays owned until the adapter and validation actually finish.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable

from pydantic import TypeAdapter, ValidationError

from backend.compiler.evaluator import evaluate, parse_bounded_json, validate_profile
from backend.compiler.policy_generator import generate_policy
from backend.config import BackendConfig
from backend.schemas import (
    LocalBenchmarkCase, NodeId, OptimizationResponse, RuntimeAdapterSpec, RuntimeAttempt,
    RuntimeAuthorization, RuntimeResult, RuntimeValidationContract, ScanResponse, content_digest,
)


class RuntimeConfigurationError(ValueError):
    """Fixed configuration failure; never include a callable, value or exception."""


class _InvalidData(ValueError):
    pass


class _DataLimit(_InvalidData):
    pass


def _encode(value, maximum):
    """Only ordinary bounded JSON values; no user serializers or object hooks."""
    chunks, ancestors = [], set()
    size = nodes = 0

    def emit(text):
        nonlocal size
        size += len(text)  # ensure_ascii below makes character and byte counts equal.
        if size > maximum:
            raise _DataLimit()
        chunks.append(text)

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if depth > 16 or nodes > 4096:
            raise _DataLimit()
        kind = type(item)
        if kind in (dict, list):
            if depth >= 16:
                raise _DataLimit()
            if id(item) in ancestors:
                raise _InvalidData()
            if len(item) > 4096:
                raise _DataLimit()
            ancestors.add(id(item))
            emit("{" if kind is dict else "[")
            for index, key in enumerate(item):
                if index:
                    emit(",")
                if kind is dict:
                    if type(key) is not str:
                        raise _InvalidData()
                    visit(key, depth + 1)
                    emit(":")
                    visit(item[key], depth + 1)
                else:
                    visit(key, depth + 1)
            emit("}" if kind is dict else "]")
            ancestors.remove(id(item))
        elif kind in (str, int, float, bool, type(None)):
            if kind is str:
                if len(item) > maximum:
                    raise _DataLimit()
                # Escape in small blocks so a huge/non-ASCII scalar cannot
                # allocate a many-times-over-budget serialized intermediate.
                emit('"')
                for offset in range(0, len(item), 1024):
                    piece = item[offset:offset + 1024]
                    piece.encode("utf-8")  # Reject unpaired surrogates.
                    emit(json.dumps(piece, ensure_ascii=True)[1:-1])
                emit('"')
                return
            if kind is int and abs(item) > 2**53 - 1:
                raise _InvalidData()
            if kind is float and not math.isfinite(item):
                raise _InvalidData()
            emit(json.dumps(item, ensure_ascii=True, allow_nan=False))
        else:
            raise _InvalidData()

    visit(value, 0)
    return "".join(chunks)


@dataclass(frozen=True)
class InvocationContext:
    """Cooperative control only; adapters must not detach work beyond their call."""

    node_id: str
    adapter: RuntimeAdapterSpec
    deadline: float
    cancellation: threading.Event

    def cancelled(self) -> bool:
        return self.cancellation.is_set() or time.monotonic() >= self.deadline


@dataclass(frozen=True)
class ExecutorRegistration:
    spec: RuntimeAdapterSpec
    operation: Callable[[object, InvocationContext], object] = field(repr=False)


class _RequestState:
    def __init__(self, node, deadline, external):
        self.node, self.deadline, self.external = node, deadline, external
        self.cancellation = threading.Event()
        self.lock = threading.RLock()
        self.attempts = ()
        self.reason = None

    def stop(self, reason=None):
        with self.lock:
            if self.reason is None:
                self.reason = reason or ("cancelled" if self.external.is_set() else
                                         "deadline_exceeded" if time.monotonic() >= self.deadline else None)
            if self.reason is not None:
                self.cancellation.set()
            return self.reason

    def result(self, status, reason, *, validation="not_run", output=None, running=False):
        with self.lock:
            last = self.attempts[-1] if self.attempts else None
            return RuntimeResult(
                node_id=self.node, status=status, reason=reason, validation_status=validation,
                selected_adapter_id=None if last is None else last.adapter_id,
                selected_model=None if last is None else last.model, provenance=None if last is None else last.provenance,
                fallback_attempted=len(self.attempts) == 2, attempt_count=len(self.attempts), attempts=self.attempts,
                worker_still_running=running, result_data=output,
            )

    def interrupted(self, reason, running=False):
        status = "cancelled" if reason == "cancelled" else "timed_out" if reason == "deadline_exceeded" else "unavailable"
        return self.result(status, reason, running=running)

    def update(self, spec, execution, validation, reason, evaluation=None):
        attempt = RuntimeAttempt(adapter_id=spec.adapter_id, model=spec.model, provenance=spec.provenance,
                                 execution_status=execution, validation_status=validation, reason=reason, evaluation=evaluation)
        with self.lock:
            self.attempts = (*self.attempts[:-1], attempt)


class CascadeRouter:
    """Library instance with immutable registrations and explicit host permission.

    A host must authenticate its optimization result, independently approve the
    exact policy/analysis digests and bind adapters. Parsed YAML grants no authority.
    No genuine executor is shipped. Test mode is explicit and cannot yield local
    provenance. Each adapter is serialized across requests within this instance.
    """

    def __init__(self, settings: BackendConfig, registrations=(), *, authorization: RuntimeAuthorization | None = None,
                 mode="local"):
        try:
            self.settings = BackendConfig.model_validate(settings)
            if type(mode) is not str or mode not in ("local", "test") or type(registrations) not in (tuple, list) or len(registrations) > 32:
                raise ValueError()
            adapters = {}
            for item in registrations:
                if type(item) is not ExecutorRegistration or not callable(item.operation):
                    raise ValueError()
                if inspect.iscoroutinefunction(item.operation) or inspect.iscoroutinefunction(getattr(item.operation, "__call__", None)):
                    raise ValueError()
                spec = RuntimeAdapterSpec.model_validate(item.spec)
                if spec.adapter_id in adapters:
                    raise ValueError()
                adapters[spec.adapter_id] = ExecutorRegistration(spec, item.operation)
            self.authorization = None if authorization is None else RuntimeAuthorization.model_validate(authorization)
        except (ValueError, TypeError, ValidationError):
            raise RuntimeConfigurationError("Runtime configuration is invalid.") from None
        self.mode = mode
        self.adapters = MappingProxyType(adapters)
        self.adapter_slots = {key: threading.BoundedSemaphore(1) for key in adapters}
        self.slots = threading.BoundedSemaphore(self.settings.job_workers)
        self.pool = ThreadPoolExecutor(max_workers=self.settings.job_workers, thread_name_prefix="cascade-local")
        self.guard = threading.RLock()
        self.active = set()
        self.closed = False

    def _routes(self, analysis, policy):
        """Validate every binding before any adapter can run; never load policy files."""
        authorization = self.authorization
        if authorization is None:
            return None, "authorization_missing"
        analysis = ScanResponse.model_validate(analysis)
        policy = OptimizationResponse.model_validate(policy)
        result, artifact = policy.result, policy.policy
        if (len(policy.model_dump_json().encode("utf-8")) > self.settings.max_job_result_bytes
                or artifact.status == "unavailable" or artifact != generate_policy(result)
                or not analysis.complete or analysis.data_source != "live"
                or analysis.analysis_id != result.plan.analysis_id or analysis.analysis_id != authorization.analysis_id
                or hashlib.sha256(analysis.model_dump_json().encode("utf-8")).hexdigest() != result.plan.analysis_digest
                or result.plan.analysis_digest != authorization.analysis_digest
                or not set(result.plan.node_ids) <= {node.node_id for node in analysis.nodes}
                or content_digest(result) != authorization.optimization_digest or artifact.digest != authorization.policy_digest):
            return None, "policy_invalid"
        if result.provenance != ("test" if self.mode == "test" else "recorded"):
            return None, "provenance_forbidden"
        decisions = {item.node_id: item for item in result.decisions if item.status in ("recommended", "baseline_retained")}
        routes = {}
        for binding in authorization.bindings:
            decision = decisions.get(binding.node_id)
            if decision is None:
                return None, "policy_invalid"
            ids = (binding.primary_adapter_id,) if binding.fallback_adapter_id is None else (binding.primary_adapter_id, binding.fallback_adapter_id)
            if len(ids) > self.settings.runtime_max_attempts:
                return None, "policy_invalid"
            registered = tuple(self.adapters.get(key) for key in ids)
            if any(item is None for item in registered):
                return None, "adapter_unavailable"
            eligible = {item.model.identifier: item.model for item in decision.candidates if item.eligibility == "eligible"}
            if (registered[0].spec.model.identifier != decision.selected_model_id
                    or len({item.spec.model.identifier for item in registered}) != len(registered)
                    or any(eligible.get(item.spec.model.identifier) != item.spec.model
                           or item.spec.evaluation_profile != result.plan.evaluation_profile
                           or item.spec.evaluation_profile_digest != result.plan.evaluation_profile_digest for item in registered)
                    or len({item.spec.output_kind for item in registered}) != 1):
                return None, "policy_invalid"
            if any(item.spec.provenance != self.mode for item in registered):
                return None, "provenance_forbidden"
            routes[binding.node_id] = registered
        return (routes, result.plan), None

    @staticmethod
    def _contract(contract, plan, route):
        if contract is None:
            return None
        contract = RuntimeValidationContract.model_validate(contract)
        profile = contract.profile
        if (profile.identifier != plan.evaluation_profile.identifier or profile.version != plan.evaluation_profile.version
                or profile.content_digest is None or profile.content_digest != plan.evaluation_profile_digest
                or any(item.spec.output_kind != contract.output_kind for item in route)
                or (profile.mechanism == "exact" and contract.output_kind != "text")):
            return None
        validate_profile(profile)
        if contract.mode == "expected_output":
            if contract.expected_output is None or len(contract.expected_output.encode("utf-8")) > 16384:
                return None
            if profile.mechanism != "exact":
                parse_bounded_json(contract.expected_output)
        elif profile.mechanism not in ("json", "json_schema") or contract.expected_output is not None:
            return None
        return contract

    def execute(self, node_id, analysis, policy, input_data, *, validation=None, cancellation=None) -> RuntimeResult:
        try:
            node_id = TypeAdapter(NodeId).validate_python(node_id)
        except ValidationError:
            raise RuntimeConfigurationError("Runtime node identifier is invalid.") from None
        if cancellation is not None and type(cancellation) is not threading.Event:
            raise RuntimeConfigurationError("Runtime cancellation requires a threading event.")
        state = _RequestState(node_id, time.monotonic() + self.settings.runtime_timeout_seconds,
                              threading.Event() if cancellation is None else cancellation)
        try:
            resolved, reason = self._routes(analysis, policy)
        except (ValueError, TypeError, KeyError, RecursionError):
            resolved, reason = None, "policy_invalid"
        if reason is not None:
            return state.result("unavailable", reason)
        routes, plan = resolved
        route = routes.get(node_id)
        if route is None:
            return state.result("unavailable", "unknown_node")
        try:
            contract = self._contract(validation, plan, route)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            contract = None
        if contract is None:
            return state.result("inconclusive", "validation_unavailable", validation="inconclusive")
        try:
            encoded = _encode(input_data, self.settings.max_request_body_bytes)
        except _DataLimit:
            return state.result("unavailable", "input_limit")
        except (ValueError, TypeError, RuntimeError):
            return state.result("unavailable", "input_invalid")
        if state.stop():
            return state.interrupted(state.reason)
        with self.guard:
            if self.closed:
                return state.result("unavailable", "closed")
            if not self.slots.acquire(blocking=False):
                return state.result("unavailable", "capacity_exceeded")
            self.active.add(state)
            try:
                future = self.pool.submit(self._work, state, route, contract, encoded)
            except Exception:
                self.active.discard(state)
                self.slots.release()
                return state.result("unavailable", "closed")
            def finished(_future):
                with self.guard:
                    self.active.discard(state)
                    self.slots.release()
            future.add_done_callback(finished)
        while True:
            if state.stop():
                future.cancel()  # Only a not-yet-started future can be cancelled this way.
                return state.interrupted(state.reason, running=future.running())
            try:
                result = future.result(timeout=0.005)
            except FutureTimeout:
                continue
            # Completion racing with cancellation/deadline cannot publish a
            # successful output after this request has stopped waiting.
            return state.interrupted(state.reason, running=future.running()) if state.stop() else result

    def _work(self, state, route, contract, encoded):
        try:
            return self._attempts(state, route, contract, encoded)
        except BaseException:
            # The registered adapter is trusted code, but even SystemExit must
            # not escape through Future.result into the host application.
            with state.lock:
                if state.attempts and state.attempts[-1].execution_status == "running":
                    spec = self.adapters[state.attempts[-1].adapter_id].spec
                    state.update(spec, "failed", "not_run", "adapter_failed")
            return state.result("failed", "adapter_failed")

    def _attempts(self, state, route, contract, encoded):
        request_deadline = state.deadline
        for registration in route:
            if state.stop():
                return state.interrupted(state.reason)
            spec = registration.spec
            slot = self.adapter_slots[spec.adapter_id]
            if not slot.acquire(blocking=False):
                return state.result("unavailable", "capacity_exceeded")
            try:
                # Preparation may consume time or race with cancellation. Do
                # not count/commit an invocation until the copy is ready.
                prepared_input = json.loads(encoded)
                with state.lock:
                    if state.stop():
                        return state.interrupted(state.reason)
                    state.deadline = min(request_deadline, time.monotonic() + spec.max_execution_seconds)
                    if state.stop():
                        return state.interrupted(state.reason)
                    state.attempts = (*state.attempts, RuntimeAttempt(
                        adapter_id=spec.adapter_id, model=spec.model, provenance=spec.provenance,
                        execution_status="running", validation_status="not_run", reason="started"))
                context = InvocationContext(state.node, spec, state.deadline, state.cancellation)
                try:
                    # A fresh copy per attempt prevents primary mutation from
                    # becoming fallback input or another request's shared state.
                    output = registration.operation(prepared_input, context)
                except BaseException:
                    state.update(spec, "failed", "not_run", "adapter_failed")
                    return state.interrupted(state.reason) if state.stop() else state.result("failed", "adapter_failed")
                state.update(spec, "succeeded", "not_run", "started")
                if state.stop():
                    return state.interrupted(state.reason)
                try:
                    output_text = _encode(output, min(self.settings.max_job_result_bytes, 16384))
                    if contract.output_kind == "text":
                        if type(output) is not str:
                            raise _InvalidData()
                        evaluation_text = output
                    else:
                        evaluation_text = output_text
                    safe_output = json.loads(output_text)
                except _DataLimit:
                    state.update(spec, "succeeded", "failed", "output_limit")
                    return state.result("failed", "output_limit", validation="failed")
                except (ValueError, TypeError, RuntimeError):
                    state.update(spec, "succeeded", "failed", "output_invalid")
                    return state.result("failed", "output_invalid", validation="failed")
                case = LocalBenchmarkCase(identifier="runtime", input_text="runtime", expected_output=contract.expected_output)
                evaluation = evaluate(case, contract.profile, evaluation_text)
                passed = evaluation.status == "passed" if contract.mode == "expected_output" else (
                    evaluation.reason == "ground_truth_unavailable" and evaluation.validation_status == "passed" and bool(evaluation.checks_ran))
                status = "passed" if passed else "failed" if evaluation.status == "failed" else "inconclusive"
                reason = "structure_validated" if passed and contract.mode == "structure" else "validated" if passed else "validation_failed" if status == "failed" else "validation_unavailable"
                state.update(spec, "succeeded", status, reason, evaluation)
                if state.stop():
                    return state.interrupted(state.reason)
                if passed:
                    return state.result("succeeded", reason, validation="passed", output=safe_output)
                if status == "inconclusive":
                    return state.result("inconclusive", reason, validation="inconclusive")
                # Only an actual validation failure can reach the explicit next
                # binding. Adapter exceptions, cancellation and limits never retry.
            finally:
                slot.release()
        return state.result("failed", "validation_failed", validation="failed")

    def close(self):
        with self.guard:
            self.closed = True
            for state in self.active:
                state.stop("closed")
        self.pool.shutdown(wait=True, cancel_futures=True)  # Honest wait; no thread termination claim.

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
