import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_scan_store
from backend.main import create_app
from backend.store import ScanStore


@pytest.fixture
def store() -> ScanStore:
    return ScanStore()


@pytest.fixture
def client(store) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_scan_store] = lambda: store
    return TestClient(app)
