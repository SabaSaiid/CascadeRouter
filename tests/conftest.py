"""Isolated, explicit local API test policy; no environment/provider setup."""

import pytest
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
import hashlib
import json

from backend.config import BackendConfig
from backend.schemas import (
    BenchmarkCaseSet, BenchmarkMeasurement, BenchmarkRegistryDocument, BenchmarkRequest,
    CountMeasurement, EvaluationProfile, LocalBenchmarkCase, ModelVersion, NumberMeasurement,
)
from backend.services.benchmark_cases import BenchmarkRegistry
from backend.services.compiler_adapter import analyze_for_api
from backend.services.repository_access import RepositoryAccess
from backend.services.storage import AnalysisStorage


SOURCE = '''from openai import OpenAI
client = OpenAI()
first = client.chat.completions.create(model="fixture/model", messages=[])
second = client.chat.completions.create(model=MODEL, messages=first)
'''


@pytest.fixture
def api_environment(tmp_path):
    root = tmp_path / "allowed"
    repository = root / "repository"
    storage = tmp_path / "storage"
    repository.mkdir(parents=True)
    storage.mkdir()
    (repository / "app.py").write_text(SOURCE, encoding="utf-8")
    settings = BackendConfig(permitted_repository_roots=[root], storage_directory=storage)
    return settings, repository, storage


def test_measurement(key, *, evaluation_status="unavailable"):
    return BenchmarkMeasurement(
        node_id=key[0], model_id=key[1], case_id=key[2], provenance="test",
        latency_ms=NumberMeasurement(availability="unavailable"),
        input_tokens=CountMeasurement(availability="unavailable"),
        output_tokens=CountMeasurement(availability="unavailable"),
        cost_usd=NumberMeasurement(availability="unavailable"), evaluation_status=evaluation_status,
    )


class DeterministicTestExecutor:
    """Lifecycle fixture only. It makes no inference or performance measurements."""

    provenance = "test"
    identity = "e" * 64
    idempotent = True

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.finished = threading.Event()
        self.cooperative = True
        self.calls = []
        self.failure = False
        self.evaluation_status = "unavailable"

    def validate_plan(self, plan):
        assert plan.provenance == "test"

    def execute(self, plan, cancellation, deadline):
        self.calls.append(plan)
        self.started.set()
        try:
            while not self.release.wait(0.01):
                if self.cooperative and cancellation.is_set():
                    return
            if self.failure:
                raise RuntimeError("PRIVATE_EXECUTOR_EXCEPTION sk-SYNTHETIC_NOT_A_CREDENTIAL")
            for key in plan.unit_keys():
                if self.cooperative and cancellation.is_set():
                    return
                yield test_measurement(key, evaluation_status=self.evaluation_status)
        finally:
            self.finished.set()


@pytest.fixture
def job_environment(api_environment):
    previous, repository, directory = api_environment
    settings = BackendConfig(permitted_repository_roots=previous.permitted_repository_roots, storage_directory=directory,
                             job_workers=1, max_queued_jobs=2, max_jobs=16)
    storage = AnalysisStorage(settings)
    analysis = analyze_for_api(str(repository), analysis_id="analysis_" + "c" * 32, timestamp=datetime.now(timezone.utc))
    storage.save(analysis)
    registry = BenchmarkRegistry(BenchmarkRegistryDocument(
        origin="test", approved=True,
        case_sets=[BenchmarkCaseSet(identifier="cases", version="v1", cases=[
            LocalBenchmarkCase(identifier="case-one", input_text="PRIVATE_LOCAL_CASE_INPUT", expected_output=None),
            LocalBenchmarkCase(identifier="case-two", input_text="PRIVATE_SECOND_CASE", expected_output=None),
        ])], evaluation_profiles=[EvaluationProfile(identifier="profile", version="v1", criteria_id="test-criteria")],
        models=[ModelVersion(identifier="local/baseline", version="v1"), ModelVersion(identifier="local/candidate", version="v1")],
    ))
    request = BenchmarkRequest(analysis_id=analysis.analysis_id, node_ids=[analysis.nodes[0].node_id],
                               baseline_model_id="local/baseline", candidate_model_ids=["local/candidate"],
                               benchmark_case_set_id="cases", evaluation_profile_id="profile")
    executor = DeterministicTestExecutor()
    yield SimpleNamespace(settings=settings, repository=repository, directory=directory, storage=storage,
                          access=RepositoryAccess(settings), analysis=analysis, registry=registry, request=request,
                          executor=executor, measurement=test_measurement)
    executor.release.set()
    storage.close()


def fixture_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@pytest.fixture
def offline_environment(job_environment):
    """All outputs/evidence in this fixture are synthetic and always labelled test."""
    from backend.schemas import (
        OfflineRecordedAnalysis, OfflineRecordedUnit, OfflineRecordingDocument, PinnedPricing,
        RecordingEvidence, VersionedReference, content_digest,
    )
    from backend.services.offline_benchmark import OfflineBenchmarkExecutor
    env = job_environment

    def pin(model):
        return type(model).model_validate({**model.model_dump(), "content_digest": content_digest(model, exclude={"content_digest"})})

    def price(model="local/baseline", **changes):
        data = dict(identifier="test-price-" + model.split("/")[-1], version="v1", model_id=model, provenance="test",
                    source_id="test-pricing-fixture", effective_at="2020-01-01T00:00:00.000000Z", currency="USD",
                    input_usd_per_million="0.10", output_usd_per_million="0.20")
        data.update(changes)
        return PinnedPricing(**data, digest=fixture_digest(data))

    def make(cases=None, profile=None, outputs=None, evidence=None, prices=()):
        cases = cases or [LocalBenchmarkCase(identifier="case-one", input_text="PRIVATE_LOCAL_INPUT", expected_output="PRIVATE_CAPTURE_ONE"),
                          LocalBenchmarkCase(identifier="case-two", input_text="PRIVATE_SECOND_INPUT", expected_output="PRIVATE_CAPTURE_TWO")]
        profile = pin(profile or EvaluationProfile(identifier="profile", version="v1", criteria_id="test-exact", mechanism="exact"))
        case_set = pin(BenchmarkCaseSet(identifier="cases", version="v1", provenance="test", validation_version="offline.v1", cases=cases))
        registry = BenchmarkRegistry(BenchmarkRegistryDocument(origin="test", approved=True, case_sets=[case_set],
                                    evaluation_profiles=[profile], models=env.registry.document.models))
        records = []
        for model in registry.document.models:
            for case in case_set.cases:
                output = case.expected_output if outputs is None else outputs.get((model.identifier, case.identifier))
                proof = RecordingEvidence(source_id="test-capture", captured_at="2026-10-28T00:00:00.000000Z")
                if evidence is not None:
                    proof = evidence(model.identifier, case.identifier)
                data = dict(recording_id="test-record-" + str(len(records)), node_id=env.request.node_ids[0],
                            model_id=model.identifier, case_id=case.identifier,
                            input_digest=hashlib.sha256(case.input_text.encode("utf-8")).hexdigest(),
                            captured_output=output, output_digest=None if output is None else hashlib.sha256(output.encode("utf-8")).hexdigest(),
                            evidence=proof.model_dump(mode="json"))
                records.append(OfflineRecordedUnit(**data, digest=fixture_digest(data)))
        group = OfflineRecordedAnalysis(analysis_id=env.analysis.analysis_id,
            analysis_digest=hashlib.sha256(env.analysis.model_dump_json().encode("utf-8")).hexdigest(),
            registry_digest=registry.identity, case_set=VersionedReference(identifier=case_set.identifier, version=case_set.version),
            evaluation_profile=VersionedReference(identifier=profile.identifier, version=profile.version), records=records)
        document = OfflineRecordingDocument(provenance="test", source_id="test-recording-fixture",
            recorded_at="2026-10-28T00:00:01.000000Z", pricing_records=prices, recordings=[group])
        return registry, document, OfflineBenchmarkExecutor(registry, document)

    env.pin = pin
    env.price = price
    env.make_offline = make
    env.registry, env.document, env.executor = make()
    return env


@pytest.fixture
def asset_environment(offline_environment, tmp_path):
    from backend.schemas import AssetApproval, BenchmarkApprovalManifest
    env = offline_environment
    data_root, operator = tmp_path / "benchmark-data", tmp_path / "operator"
    data_root.mkdir()
    operator.mkdir()
    registry_path, recording_path = data_root / "registry.json", data_root / "recordings.json"
    registry_path.write_text(env.registry.document.model_dump_json(), encoding="utf-8")
    recording_path.write_text(env.document.model_dump_json(), encoding="utf-8")
    manifest = BenchmarkApprovalManifest(approved_by="test-operator", approved_at="2026-10-28T00:01:00.000000Z", assets=[
        AssetApproval(asset_id="test-registry", root_index=0, relative_path="registry.json", kind="registry", provenance="test",
                      digest=hashlib.sha256(registry_path.read_bytes()).hexdigest()),
        AssetApproval(asset_id="test-recordings", root_index=0, relative_path="recordings.json", kind="offline_recordings", provenance="test",
                      digest=hashlib.sha256(recording_path.read_bytes()).hexdigest()),
    ])
    manifest_path = operator / "approvals.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    env.settings = BackendConfig(**{**env.settings.model_dump(), "permitted_repository_roots": env.settings.permitted_repository_roots,
        "storage_directory": env.directory, "permitted_benchmark_data_roots": [data_root],
        "benchmark_registry_path": registry_path, "benchmark_recordings_path": recording_path,
        "benchmark_approval_manifest_path": manifest_path})
    def configure(**changes):
        return BackendConfig(**{**env.settings.model_dump(), "permitted_repository_roots": env.settings.permitted_repository_roots,
            "storage_directory": env.directory, "permitted_benchmark_data_roots": [data_root],
            "benchmark_registry_path": registry_path, "benchmark_recordings_path": recording_path,
            "benchmark_approval_manifest_path": manifest_path, **changes})
    env.configure = configure
    env.data_root, env.registry_path, env.recording_path, env.manifest_path = data_root, registry_path, recording_path, manifest_path
    return env


@pytest.fixture
def optimization_environment(offline_environment):
    """Synthetic captures always retain test provenance, including policy tests."""
    from decimal import Decimal
    from backend.compiler.metrics import aggregate
    from backend.compiler.router_optimizer import OptimizationSnapshot
    from backend.schemas import BenchmarkSummary, RecordingEvidence, VersionedReference
    env = offline_environment

    def build(*, rates=None, outputs=None, cases=None, profile=None, latency=None, tokens=1000000):
        rates = rates if rates is not None else {"local/baseline": "1.00", "local/candidate": "0.50"}
        prices = tuple(env.price(model, input_usd_per_million=rate, output_usd_per_million="0")
                       for model, rate in rates.items() if rate is not None)
        price_map = {price.model_id: price for price in prices}
        def evidence(model, case):
            price = price_map.get(model)
            return RecordingEvidence(source_id="test-optimization-capture", captured_at="2026-10-28T00:00:00Z",
                input_tokens=tokens, output_tokens=0, latency_ms=latency,
                pricing_reference=None if price is None else VersionedReference(identifier=price.identifier, version=price.version))
        registry, document, executor = env.make_offline(cases=cases, profile=profile, outputs=outputs, evidence=evidence, prices=prices)
        plan = registry.resolve(env.request, env.analysis, env.settings, executor)
        job = env.storage.create_job(env.request, plan, lambda _: None)
        env.storage.transition_job(job.run_id, ("queued",), status="running")
        records = tuple(executor.execute(plan, threading.Event(), datetime.max.replace(tzinfo=timezone.utc)))
        for record in records:
            env.storage.transition_job(job.run_id, ("running",), measurement=record)
        statuses = {item.evaluation_status for item in records}
        summary = BenchmarkSummary(provenance="test", evaluation_status="failed" if "failed" in statuses else "passed" if statuses == {"passed"} else "inconclusive",
                                   metrics=aggregate(plan, records))
        job = env.storage.transition_job(job.run_id, ("running",), status="complete", result=summary)
        return SimpleNamespace(registry=registry, document=document, executor=executor, job=job,
            snapshot=OptimizationSnapshot(job, Decimal("0.92"), "a" * 64))
    env.build_optimization = build
    return env
