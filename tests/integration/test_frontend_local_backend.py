"""Real loopback transport integration, with target bytes checked before/after."""
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from backend.config import BackendConfig
from backend.main import create_app


def test_typescript_client_against_real_local_backend(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node 24+ is required for the TypeScript local transport test")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.lstrip("v").split(".")[0]) < 24:
        pytest.skip("Node 24+ is required for native TypeScript execution")
    repository = tmp_path / "repository"
    storage = tmp_path / "storage"
    repository.mkdir()
    storage.mkdir()
    # Importing or executing this target would fail. It is only parsed by the scanner.
    source = repository / "app.py"
    original = b'raise RuntimeError("TARGET_MUST_NEVER_EXECUTE")\nfrom openai import OpenAI\nclient = OpenAI()\nresponse = client.chat.completions.create(model="local/baseline", messages=[])\n'
    source.write_bytes(original)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(BackendConfig(bind_port=port, permitted_repository_roots=[repository], storage_directory=storage))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Local contract test backend did not start"
        script = Path(__file__).resolve().parents[2] / "frontend/tests/live-backend.mjs"
        completed = subprocess.run([node, str(script), f"http://127.0.0.1:{port}", str(repository)], capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, "Local TypeScript contract integration failed: " + completed.stderr
        assert "Real local backend:" in completed.stdout
        assert source.read_bytes() == original
        assert sorted(path.name for path in repository.iterdir()) == ["app.py"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
    assert not thread.is_alive(), "Local contract test backend did not stop"
