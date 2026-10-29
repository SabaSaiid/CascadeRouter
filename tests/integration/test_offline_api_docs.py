"""API discovery must not serve documentation pages that fetch remote assets."""
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.schemas import ErrorResponse


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_remote_asset_documentation_pages_are_not_served(path):
    with TestClient(create_app(), base_url="http://localhost") as client:
        response = client.get(path)
        assert response.status_code == 404
        error = ErrorResponse.model_validate_json(response.content)
        assert error.code == "not_found" and error.request_id is not None
        contract = client.get("/openapi.json")
        assert contract.status_code == 200
        assert "/api/scan" in contract.json()["paths"]
        assert "/api/patches/{patch_id}/validate" in contract.json()["paths"]
