import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_llm_client_factory, get_run_store, get_scan_store, get_spend_tracker
from backend.guardrails import SpendTracker
from backend.main import create_app
from backend.services.llm import CompletionResult
from backend.store import RunStore, ScanStore


class FakeLLM:
    """Test double for Nebius: answers each sample-repo prompt; small models fail synthesis."""

    def __init__(self):
        self.calls = []

    async def complete(self, model, messages, params):
        self.calls.append(model)
        text = messages[-1]["content"]
        big = "Super" in model or "Ultra" in model
        if text == "Generate fix":
            out = ("1. Close the app.\n2. Run it as administrator and reopen the project; "
                   "error 0x80070005 means access was denied.") if big else "Try again."
        elif "Extract metadata" in text:
            out = '{"account_id": "ACC-48213", "os_version": "Windows 11 23H2", "error_code": "SYNC-503"}' \
                if "ACC-48213" in text else '{"account_id": "77120", "os_version": "macOS 15.1", "error_code": ""}'
        elif "charged" in text:
            out = '{"category": "billing", "confidence": 0.95}'
        elif "crashes" in text:
            out = '{"category": "tech_support", "confidence": 0.9}'
        else:
            out = '{"category": "general", "confidence": 0.8}'
        latency = 1200.0 if "Ultra" in model else 400.0 if "Super" in model else 150.0
        return CompletionResult(out, 300, 40, True, latency, latency / 4)


@pytest.fixture
def store() -> ScanStore:
    return ScanStore()


@pytest.fixture
def runs() -> RunStore:
    return RunStore()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(store, runs, fake_llm):
    app = create_app()
    app.dependency_overrides[get_scan_store] = lambda: store
    app.dependency_overrides[get_run_store] = lambda: runs
    app.dependency_overrides[get_spend_tracker] = lambda: SpendTracker(10.0)
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda settings, tracker: fake_llm)
    with TestClient(app, base_url="http://localhost") as c:
        yield c
