"""In-process HTTP only; no model providers, live sockets or target execution."""

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.compiler.dag_builder import analyze_repository
from backend.config import BackendConfig, ConfigurationError
from backend.main import create_app, load_settings
from backend.schemas import ErrorResponse, ScanResponse
from backend.services import compiler_adapter


def client_for(settings=None):
    return TestClient(create_app(settings), base_url="http://localhost")


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    value = ErrorResponse.model_validate_json(response.content)
    assert value.code == code and value.request_id.startswith("req_")
    return value


def test_real_scan_flat_contract_stable_ids_graph_and_retrieval(api_environment):
    settings, repository, _ = api_environment
    internal = analyze_repository(str(repository))
    with client_for(settings) as client:
        health = client.get("/api/health").json()
        assert health["scan_available"] and not health["benchmark_available"] and not health["optimization_available"]
        response = client.post("/api/scan", json={"repository_path": "repository"})
        assert response.status_code == 200
        public = ScanResponse.model_validate_json(response.content)
        assert public.repository_path == repository.as_posix() and public.data_source == "live"
        assert public.complete and public.total_source_bytes_read > 0
        assert [node.node_id for node in public.nodes] == [node.node_id for node in internal.scan_result.nodes]
        assert public.graph_edges == tuple((edge.from_node_id, edge.to_node_id) for edge in internal.workflow_graph.edges)
        assert public.nodes[1].current_model is None
        retrieved = client.get("/api/analyses/" + public.analysis_id)
        assert retrieved.status_code == 200 and retrieved.content == response.content
        (repository / "app.py").write_text("# changed after snapshot\n", encoding="utf-8")
        assert client.get("/api/analyses/" + public.analysis_id).content == response.content
    with client_for(settings) as restarted:
        assert restarted.get("/api/analyses/" + public.analysis_id).content == response.content


def test_partial_errors_preserve_separate_diagnostics(api_environment):
    settings, repository, _ = api_environment
    (repository / "invalid.py").write_text("def invalid(:", encoding="utf-8")
    with client_for(settings) as client:
        response = client.post("/api/scan", json={"repository_path": "repository"})
        assert response.status_code == 200
        result = ScanResponse.model_validate_json(response.content)
        assert len(result.nodes) == 2 and not result.complete
        assert not result.scan_complete and not result.graph_complete
        assert result.scan_diagnostics[0].code == "syntax_error"
        assert "input_scan_incomplete" in {item.code for item in result.graph_diagnostics}


@pytest.mark.parametrize("payload", [None, [], "code", {}, {"repository_path": None}, {"repository_path": 1},
                                      {"repository_path": True}, {"repository_path": " "},
                                      {"repository_path": "repository", "source": "PRIVATE_PAYLOAD"},
                                      {"repository_path": "repository", "command": "PRIVATE_COMMAND"}])
def test_invalid_request_and_extra_fields_are_safe(api_environment, payload):
    with client_for(api_environment[0]) as client:
        response = client.post("/api/scan", json=payload)
        assert_error(response, 422, "invalid_request")
        assert "PRIVATE" not in response.text and "input" not in response.json()


@pytest.mark.parametrize("kind", ["outside", "traversal", "missing", "file"])
def test_authorization_status_mapping_and_no_path_disclosure(api_environment, kind):
    settings, _, storage = api_environment
    path, code, status = {
        "outside": (str(storage), "repository_forbidden", 403),
        "traversal": ("../PRIVATE_PATH", "repository_forbidden", 403),
        "missing": ("PRIVATE_MISSING", "repository_unavailable", 422),
        "file": ("repository/app.py", "repository_unavailable", 422),
    }[kind]
    with client_for(settings) as client:
        response = client.post("/api/scan", json={"repository_path": path})
        assert_error(response, status, code)
        assert "PRIVATE" not in response.text and str(storage) not in response.text


@pytest.mark.parametrize("policy", ["none", "roots_only", "storage_only"])
def test_missing_configuration_is_unavailable(api_environment, policy):
    settings, _, storage = api_environment
    config = {"none": BackendConfig(), "roots_only": BackendConfig(permitted_repository_roots=settings.permitted_repository_roots),
              "storage_only": BackendConfig(storage_directory=storage)}[policy]
    with client_for(config) as client:
        health = client.get("/api/health").json()
        assert not health["scan_available"] and health["configuration_required"]
        assert_error(client.post("/api/scan", json={"repository_path": "."}), 503, "capability_unavailable")


def test_invalid_and_missing_analysis_ids_and_unknown_route(api_environment):
    with client_for(api_environment[0]) as client:
        assert_error(client.get("/api/analyses/analysis_" + "0" * 32), 404, "not_found")
        assert_error(client.get("/api/analyses/PRIVATE_INVALID_ID"), 422, "invalid_request")
        assert_error(client.get("/api/missing"), 404, "not_found")


def test_source_is_never_executed_and_private_text_is_not_exported(api_environment):
    settings, repository, storage = api_environment
    marker = storage / "MUST_NOT_EXIST"
    (repository / "payload.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "raise RuntimeError('PRIVATE_SOURCE_EXCEPTION')\n", encoding="utf-8")
    (repository / "private.py").write_text('''from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="sk-PRIVATE_TOKEN", messages=[{"role":"user", "content":"PRIVATE_PROMPT"}])
''', encoding="utf-8")
    with client_for(settings) as client:
        response = client.post("/api/scan", json={"repository_path": "repository"})
        assert response.status_code == 200 and not marker.exists()
        assert "PRIVATE_PROMPT" not in response.text and "PRIVATE_TOKEN" not in response.text
        assert "PRIVATE_SOURCE_EXCEPTION" not in response.text
    assert not marker.exists()
    assert b"PRIVATE_PROMPT" not in (storage / "analyses.sqlite3").read_bytes()


def test_unexpected_exception_is_fixed_and_not_logged_raw(api_environment, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE_EXCEPTION /PRIVATE/PATH sk-SYNTHETIC")

    monkeypatch.setattr(compiler_adapter, "analyze_for_api", broken)
    with client_for(api_environment[0]) as client:
        response = client.post("/api/scan", json={"repository_path": "repository"})
        assert_error(response, 500, "internal_error")
        assert "PRIVATE" not in response.text and "PRIVATE" not in caplog.text
        assert "sk-SYNTHETIC" not in caplog.text


def test_declared_body_limit_and_invalid_json(api_environment):
    settings = BackendConfig(permitted_repository_roots=api_environment[0].permitted_repository_roots,
                             storage_directory=api_environment[2], max_request_body_bytes=64)
    with client_for(settings) as client:
        assert_error(client.post("/api/scan", content=b"x", headers={"content-length": "65"}), 413, "request_too_large")
        assert_error(client.post("/api/scan", content=b"{"), 422, "invalid_request")
        assert_error(client.post("/api/scan", content=b"\xff", headers={"content-type": "application/json"}), 422, "invalid_request")


def test_streamed_body_limits_count_actual_chunks_even_with_false_length(api_environment, monkeypatch):
    settings = BackendConfig(max_request_body_bytes=32)
    app = create_app(settings)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected body must not reach compiler work.")

    monkeypatch.setattr(compiler_adapter, "analyze_for_api", forbidden)

    async def request(chunks, extra_headers):
        sent = []
        messages = [{"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
                    for index, chunk in enumerate(chunks)]

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                 "scheme": "http", "path": "/api/scan", "raw_path": b"/api/scan", "query_string": b"",
                 "root_path": "", "server": ("localhost", 8000), "client": ("127.0.0.1", 1234),
                 "headers": [(b"host", b"localhost"), (b"content-type", b"application/json"), *extra_headers]}
        await app(scope, receive, send)
        return sent[0]["status"], json.loads(b"".join(item.get("body", b"") for item in sent[1:]))

    for headers in ([], [(b"transfer-encoding", b"chunked")], [(b"content-length", b"1")]):
        status, result = asyncio.run(request([b"x" * 16, b"x" * 17], headers))
        assert status == 413 and result["code"] == "request_too_large"
    for headers in ([(b"content-length", b"1"), (b"content-length", b"2")],
                    [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
                    [(b"content-length", b"bad")], [(b"content-length", b"4")]):
        status, result = asyncio.run(request([b"{}"], headers))
        assert status == 422 and result["code"] == "invalid_request"


def test_deadline_retains_capacity_until_thread_finishes_and_does_not_store(api_environment, monkeypatch):
    original = compiler_adapter.analyze_for_api
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(10), "Test did not release compiler thread."
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(compiler_adapter, "analyze_for_api", slow)
    settings = BackendConfig(permitted_repository_roots=api_environment[0].permitted_repository_roots,
                             storage_directory=api_environment[2], scan_timeout_seconds=1)
    with client_for(settings) as client:
        try:
            assert_error(client.post("/api/scan", json={"repository_path": "repository"}), 503, "capability_unavailable")
            assert entered.is_set() and not finished.is_set()
            assert_error(client.post("/api/scan", json={"repository_path": "repository"}), 429, "capacity_exceeded")
        finally:
            release.set()
        assert finished.wait(5)
        monkeypatch.setattr(compiler_adapter, "analyze_for_api", original)
        for _ in range(100):
            response = client.post("/api/scan", json={"repository_path": "repository"})
            if response.status_code != 429:
                break
            time.sleep(0.01)
        assert response.status_code == 200
    import sqlite3
    with sqlite3.connect(api_environment[2] / "analyses.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1


def test_concurrent_http_scans_persist_distinct_snapshots(api_environment):
    settings = BackendConfig(permitted_repository_roots=api_environment[0].permitted_repository_roots,
                             storage_directory=api_environment[2], scan_workers=4)
    with client_for(settings) as client:
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(lambda _: client.post("/api/scan", json={"repository_path": "repository"}), range(4)))
        assert all(response.status_code == 200 for response in responses)
        assert len({response.json()["analysis_id"] for response in responses}) == 4
        for response in responses:
            assert client.get("/api/analyses/" + response.json()["analysis_id"]).content == response.content


def test_openapi_contract_and_origin_host_boundaries(api_environment):
    with client_for(api_environment[0]) as client:
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/scan"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/ScanRequest")
        assert schema["paths"]["/api/scan"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
        assert schema["components"]["schemas"]["ScanResponse"]["additionalProperties"] is False
        assert_error(client.get("/api/health", headers={"host": "attacker.invalid"}), 422, "invalid_request")
        assert_error(client.post("/api/scan", json={"repository_path": "repository"}, headers={"origin": "https://attacker.invalid"}), 422, "invalid_request")
        response = client.get("/api/health", headers={"origin": "http://localhost:5173"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        response = client.post("/api/scan", json={"repository_path": "../outside"}, headers={"origin": "http://localhost:5173"})
        assert_error(response, 403, "repository_forbidden")
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_explicit_nonsecret_json_loader_and_sanitized_config_errors(api_environment, tmp_path):
    settings, _, storage = api_environment
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"permitted_repository_roots": [str(settings.permitted_repository_roots[0])],
                                "storage_directory": str(storage)}), encoding="utf-8")
    assert load_settings(str(path)).storage_directory == storage
    for text in ('{"api_key":"PRIVATE_CREDENTIAL"}', '{"bind_host":"0.0.0.0"}', "PRIVATE_INVALID_JSON", '"PRIVATE_STRING"'):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ConfigurationError) as error:
            load_settings(str(path))
        assert "PRIVATE" not in str(error.value) and str(path) not in str(error.value)
    with pytest.raises(ConfigurationError):
        load_settings("relative.json")


def test_preflight_failures_have_controlled_error_bodies(api_environment):
    with client_for(api_environment[0]) as client:
        headers = {"origin": "http://localhost:5173", "access-control-request-method": "POST",
                   "access-control-request-headers": "Content-Type"}
        assert client.options("/api/scan", headers=headers).status_code == 200
        for changes in ({"access-control-request-method": "DELETE"}, {"access-control-request-headers": "Authorization"}):
            response = client.options("/api/scan", headers={**headers, **changes})
            assert_error(response, 422, "invalid_request")
            assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_source_changed_between_compiler_passes_returns_conflict(api_environment, monkeypatch):
    from backend.compiler import dag_builder
    original = dag_builder.build_workflow_graph
    repository = api_environment[1]

    def changed(path, scan_result, options=None):
        source = repository / "app.py"
        source.write_text(source.read_text(encoding="utf-8").replace("fixture/model", "fixture/changed"), encoding="utf-8")
        return original(path, scan_result, options=options)

    monkeypatch.setattr(dag_builder, "build_workflow_graph", changed)
    with client_for(api_environment[0]) as client:
        assert_error(client.post("/api/scan", json={"repository_path": "repository"}), 409, "source_conflict")


def test_changed_root_http_error_is_conflict(api_environment):
    settings, repository, _ = api_environment
    with client_for(settings) as client:
        root = repository.parent
        root.rename(root.with_name("previous"))
        root.mkdir()
        (root / "repository").mkdir()
        assert_error(client.post("/api/scan", json={"repository_path": "repository"}), 409, "source_conflict")


def test_retrieval_reapplies_current_root_policy(api_environment, tmp_path):
    settings, _, storage = api_environment
    with client_for(settings) as client:
        response = client.post("/api/scan", json={"repository_path": "repository"})
        assert response.status_code == 200
    other_root = tmp_path / "other-policy"
    other_root.mkdir()
    with client_for(BackendConfig(permitted_repository_roots=[other_root], storage_directory=storage)) as client:
        assert_error(client.get("/api/analyses/" + response.json()["analysis_id"]), 403, "repository_forbidden")


def test_duplicate_transport_id_cannot_overwrite_existing_http_snapshot(api_environment, monkeypatch):
    from types import SimpleNamespace
    from backend.services import scan_service
    monkeypatch.setattr(scan_service, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    with client_for(api_environment[0]) as client:
        first = client.post("/api/scan", json={"repository_path": "repository"})
        assert first.status_code == 200
        (api_environment[1] / "app.py").write_text("# different repository content\n", encoding="utf-8")
        assert_error(client.post("/api/scan", json={"repository_path": "repository"}), 409, "source_conflict")
        assert client.get("/api/analyses/" + first.json()["analysis_id"]).content == first.content


def test_supported_entry_point_is_loopback_and_bad_configuration_exits_safely(api_environment, tmp_path, monkeypatch, capsys):
    import sys
    from types import SimpleNamespace
    from backend import main as entry

    invoked = []
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *args, **kwargs: invoked.append(kwargs)))
    path = tmp_path / "explicit.json"
    path.write_text(json.dumps({"permitted_repository_roots": [str(api_environment[1].parent)],
                                "storage_directory": str(api_environment[2])}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["backend.main", "--config", str(path)])
    assert entry.main() == 0
    assert invoked == [{"host": "127.0.0.1", "port": 8000, "access_log": False}]
    path.write_text('{"api_key":"PRIVATE_STARTUP_INPUT"}', encoding="utf-8")
    assert entry.main() == 2
    assert len(invoked) == 1
    output = capsys.readouterr().out
    assert "PRIVATE_STARTUP_INPUT" not in output and str(path) not in output
