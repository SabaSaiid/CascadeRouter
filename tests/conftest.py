"""Isolated, explicit local API test policy; no environment/provider setup."""

import pytest
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

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
