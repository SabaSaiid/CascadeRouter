"""Local fixtures never become production defaults or genuine recorded evidence."""

import threading
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.config import BackendConfig
from backend.schemas import (
    BenchmarkMeasurement, BenchmarkRegistryDocument, BenchmarkRequest, LocalBenchmarkCase,
    NumberMeasurement, OfflineRecordingDocument, RecordedAnalysisResults, RecordingDocument,
    ScanResponse,
)
from backend.services.benchmark_cases import BenchmarkRegistry, ReplayExecutor, digest, load_local_assets
from backend.services.errors import ServiceError
from backend.services.offline_benchmark import OfflineBenchmarkExecutor


def test_versioned_plan_is_immutable_and_excludes_case_source(job_environment):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    assert plan.case_set.version == plan.evaluation_profile.version == "v1"
    assert plan.models[0].identifier == env.request.baseline_model_id
    assert plan.analysis_digest == digest(env.analysis.model_dump_json().encode("utf-8"))
    assert plan.provenance == "test" and len(plan.unit_keys()) == 4
    assert "PRIVATE_" not in plan.model_dump_json()
    with pytest.raises(ValidationError):
        plan.case_ids = ("changed",)


@pytest.mark.parametrize("field", ["benchmark_case_set_id", "evaluation_profile_id", "baseline_model_id"])
def test_unknown_registry_references_rejected(job_environment, field):
    env = job_environment
    request = BenchmarkRequest.model_validate({**env.request.model_dump(), field: "unknown"})
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(request, env.analysis, env.settings, env.executor)
    assert error.value.code == "invalid_request"


def test_incomplete_analysis_unknown_nodes_and_excessive_work_fail_closed(job_environment):
    env = job_environment
    partial = ScanResponse.model_validate({**env.analysis.model_dump(), "graph_complete": False, "complete": False})
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(env.request, partial, env.settings, env.executor)
    assert error.value.code == "source_conflict"
    mock = ScanResponse.model_validate({**env.analysis.model_dump(), "data_source": "mock"})
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(env.request, mock, env.settings, env.executor)
    assert error.value.code == "source_conflict"
    unknown = BenchmarkRequest.model_validate({**env.request.model_dump(), "node_ids": ["llm_" + "0" * 24]})
    with pytest.raises(ServiceError):
        env.registry.resolve(unknown, env.analysis, env.settings, env.executor)
    settings = BackendConfig(max_benchmark_units=1)
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(env.request, env.analysis, settings, env.executor)
    assert error.value.code == "capacity_exceeded"


@pytest.mark.parametrize("change", [
    {"node_ids": []}, {"node_ids": ["bad"]}, {"node_ids": ["llm_" + "1" * 24] * 2},
    {"node_ids": ["llm_" + "1" * 24] * 17}, {"candidate_model_ids": []},
    {"candidate_model_ids": ["local/baseline"]}, {"candidate_model_ids": ["other"] * 9},
    {"baseline_model_id": "sk-PRIVATE_TOKEN"}, {"analysis_id": 1}, {"command": "PRIVATE_COMMAND"},
    {"benchmark_case_set_id": "../cases"}, {"idempotency_key": "PRIVATE key"},
])
def test_strict_bounded_requests(job_environment, change):
    with pytest.raises(ValidationError):
        BenchmarkRequest.model_validate({**job_environment.request.model_dump(), **change})


@pytest.mark.parametrize("values", [
    {"availability": "unavailable", "value": 0.0}, {"availability": "available", "value": None},
    {"availability": "available", "value": -1.0}, {"availability": "available", "value": float("nan")},
    {"availability": "available", "value": "1"}, {"availability": "available", "value": True},
])
def test_measurement_availability_never_fills_missing_values(values):
    with pytest.raises(ValidationError):
        NumberMeasurement(**values)


def test_test_replay_preserves_records_without_relabelling_or_filling_missing_units(job_environment):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    units = tuple(env.measurement(key) for key in plan.unit_keys())
    record = RecordedAnalysisResults(analysis_id=plan.analysis_id, analysis_digest=plan.analysis_digest,
                                     registry_digest=plan.registry_digest, case_set=plan.case_set,
                                     evaluation_profile=plan.evaluation_profile, measurements=units)
    document = RecordingDocument(provenance="test", approved=True, source_id="test-fixture",
                                 recorded_at=datetime.now(timezone.utc), recordings=[record])
    executor = ReplayExecutor(document)
    replay_plan = env.registry.resolve(env.request, env.analysis, env.settings, executor)
    import threading
    actual = tuple(executor.execute(replay_plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc)))
    assert actual == units and all(item.provenance == "test" for item in actual)
    assert all(item.latency_ms.value is None and item.cost_usd.value is None and item.quality_score is None for item in actual)
    partial = RecordingDocument.model_validate({**document.model_dump(), "recordings": [
        {**record.model_dump(), "measurements": units[:1]},
    ]})
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(env.request, env.analysis, env.settings, ReplayExecutor(partial))
    assert error.value.code == "capability_unavailable"
    with pytest.raises(ValidationError):
        RecordingDocument.model_validate({**document.model_dump(), "provenance": "recorded"})


def test_unconfigured_and_test_assets_cannot_enable_production(job_environment, tmp_path):
    assert load_local_assets(BackendConfig()) == (None, None)
    path = tmp_path / "registry.json"
    path.write_text(job_environment.registry.document.model_dump_json(), encoding="utf-8")
    settings = BackendConfig(benchmark_registry_path=path)
    with pytest.raises(ServiceError):
        load_local_assets(settings)
    data = job_environment.registry.document.model_dump()
    data["case_sets"] = data["case_sets"] * 2
    with pytest.raises(ValidationError):
        BenchmarkRegistryDocument.model_validate(data)
    path.write_text("PRIVATE_INVALID_ASSET", encoding="utf-8")
    with pytest.raises(ServiceError) as error:
        load_local_assets(settings)
    assert "PRIVATE" not in str(error.value)


def test_recorded_profile_cannot_invent_success_from_unavailable_evaluations(job_environment):
    measurement = job_environment.measurement((job_environment.request.node_ids[0], "local/baseline", "case-one"))
    with pytest.raises(ValidationError):
        BenchmarkMeasurement.model_validate({**measurement.model_dump(), "quality_score": 1.0})


@pytest.mark.parametrize("approval", [1, 0, "true", False, None])
def test_asset_approval_cannot_be_coerced(job_environment, approval):
    with pytest.raises(ValidationError):
        BenchmarkRegistryDocument.model_validate({**job_environment.registry.document.model_dump(), "approved": approval})


def test_offline_replay_uses_unit_identity_and_plan_order_not_input_or_storage_order(offline_environment):
    env = offline_environment
    cases = [LocalBenchmarkCase(identifier="case-z", input_text="same test input", expected_output="first"),
             LocalBenchmarkCase(identifier="case-a", input_text="same test input", expected_output="second")]
    outputs = {(model.identifier, case.identifier): case.expected_output
               for model in env.registry.document.models for case in cases}
    outputs[("local/candidate", "case-z")] = "test-only incorrect response"
    registry, document, _ = env.make_offline(cases=cases, outputs=outputs)
    data = document.model_dump(mode="json")
    data["recordings"][0]["records"].reverse()
    executor = OfflineBenchmarkExecutor(registry, OfflineRecordingDocument.model_validate(data))
    plan = registry.resolve(env.request, env.analysis, env.settings, executor)
    records = {record.unit_key(): record for record in document.recordings[0].records}

    iterator = executor.execute(plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc))
    actual = tuple(iterator)

    assert tuple(item.unit_key() for item in actual) == plan.unit_keys()
    assert plan.case_ids == ("case-z", "case-a")
    for item in actual:
        original = records[item.unit_key()]
        assert item.provenance == "test" and item.output_available
        assert (item.recording_id, item.evidence_digest) == (original.recording_id, original.digest)
        expected = "failed" if item.unit_key()[1:] == ("local/candidate", "case-z") else "passed"
        assert item.evaluation_status == expected
    # Exhaustion remains exhaustion, including repeated reads of the iterator.
    for _ in range(2):
        with pytest.raises(StopIteration):
            next(iterator)


@pytest.mark.parametrize("missing_index", [0, -1])
def test_offline_replay_rejects_missing_units_before_evaluation(offline_environment, monkeypatch, missing_index):
    env = offline_environment
    data = env.document.model_dump(mode="json")
    data["recordings"][0]["records"].pop(missing_index)
    executor = OfflineBenchmarkExecutor(env.registry, OfflineRecordingDocument.model_validate(data))

    def unexpected_evaluation(*args):
        pytest.fail("Incomplete recordings must be rejected before any evaluation.")

    monkeypatch.setattr("backend.services.offline_benchmark.evaluate", unexpected_evaluation)
    with pytest.raises(ServiceError) as error:
        env.registry.resolve(env.request, env.analysis, env.settings, executor)
    assert error.value.code == "source_conflict"


@pytest.mark.parametrize("change,code", [
    ({"analysis_id": "analysis_" + "b" * 32}, "capability_unavailable"),
    ({"analysis_digest": "b" * 64}, "capability_unavailable"),
    ({"node_ids": ["llm_" + "b" * 24]}, "source_conflict"),
    ({"case_set": {"identifier": "cases", "version": "v2"}}, "capability_unavailable"),
    ({"evaluation_profile": {"identifier": "profile", "version": "v2"}}, "capability_unavailable"),
    ({"case_set_digest": "b" * 64}, "source_conflict"),
    ({"evaluation_profile_digest": "b" * 64}, "source_conflict"),
    ({"case_ids": ["case-two", "case-one"]}, "source_conflict"),
])
def test_offline_replay_rejects_stale_plan_associations_before_yielding(offline_environment, change, code):
    env = offline_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    stale = type(plan).model_validate({**plan.model_dump(), **change})
    iterator = env.executor.execute(stale, threading.Event(), datetime.max.replace(tzinfo=timezone.utc))
    with pytest.raises(ServiceError) as error:
        next(iterator)
    assert error.value.code == code
