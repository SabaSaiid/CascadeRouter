from backend.config import REPO_ROOT


def test_scan_sample_repo(client, store):
    res = client.post("/api/scan", json={"repository_path": "tests/fixtures/sample_repo"})
    assert res.status_code == 200
    body = res.json()
    assert body["repository_path"] == "tests/fixtures/sample_repo"
    assert body["data_source"] == "live"
    assert body["scanned_files_count"] == 2
    assert body["detected_framework"] == "OpenAI SDK"
    assert [n["node_id"] for n in body["nodes"]] == [
        "node_classify_customer_intent",
        "node_extract_ticket_metadata",
        "node_generate_support_resolution",
    ]
    assert body["graph_edges"][0] == ["node_classify_customer_intent", "node_extract_ticket_metadata"]
    assert body["nodes"][0]["expected_schema"]["required"] == ["category", "confidence"]
    assert body["timestamp"].endswith("+00:00")

    stored = store.latest()
    assert stored is not None and stored.result.model_dump(mode="json") == body
    assert store.find_by_node_ids(["node_extract_ticket_metadata"]) is stored
    assert store.find_by_node_ids(["node_missing"]) is None


def test_scan_absolute_path(client):
    res = client.post("/api/scan", json={"repository_path": str(REPO_ROOT / "tests/fixtures/sample_repo")})
    assert res.status_code == 200 and len(res.json()["nodes"]) == 3


def test_scan_rejects_paths_outside_root(client):
    for path in ("/etc", "../", "nope/missing"):
        res = client.post("/api/scan", json={"repository_path": path})
        assert res.status_code == 400, path
        assert "detail" in res.json()


def test_scan_validates_body(client):
    assert client.post("/api/scan", json={}).status_code == 422
    assert client.post("/api/scan", json={"repository_path": ""}).status_code == 422
    assert client.post("/api/scan", json={"repository_path": "x", "extra": 1}).status_code == 422


def test_scan_respects_allowed_roots(monkeypatch, store):
    from fastapi.testclient import TestClient

    from backend.api.deps import get_scan_store
    from backend.main import create_app

    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", "tests/fixtures")
    app = create_app()
    app.dependency_overrides[get_scan_store] = lambda: store
    c = TestClient(app, base_url="http://localhost")
    assert c.post("/api/scan", json={"repository_path": "tests/fixtures/sample_repo"}).status_code == 200
    assert c.post("/api/scan", json={"repository_path": "backend"}).status_code == 400


def test_scan_rejects_overlong_path_with_422(client):
    assert client.post("/api/scan", json={"repository_path": "a/" * 600}).status_code == 422


def test_scan_drops_asts_but_keeps_sources(client, store):
    client.post("/api/scan", json={"repository_path": "tests/fixtures/sample_repo"})
    stored = store.latest()
    assert stored.repo.trees == {} and "agent/workflow.py" in stored.repo.sources
