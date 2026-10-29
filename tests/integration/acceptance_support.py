"""Run only first-party clients against the real explicitly configured loopback API."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest
import uvicorn

from backend.main import create_app


def node24():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node 24+ unavailable for native TypeScript client acceptance")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.lstrip("v").split(".")[0]) < 24:
        pytest.skip("Node 24+ unavailable for native TypeScript client acceptance")
    return node


@contextmanager
def serve(settings, **injections):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(settings, **injections)
    # Match the supported entry point: forwarding headers grant no peer authority.
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
                                          ws="none", log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Local acceptance backend did not start"
        yield SimpleNamespace(base=f"http://127.0.0.1:{port}", app=app)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
    assert not thread.is_alive(), "Local acceptance backend did not stop"


def client_case(base, name, payload):
    folder = Path(__file__).resolve().parents[2] / "frontend/tests/acceptance"
    script = (folder / name).resolve(strict=True)
    assert script.parent == folder and script.suffix == ".mjs", "Only first-party acceptance scripts may run"
    completed = subprocess.run([node24(), str(script), base], input=json.dumps(payload),
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, "Local client acceptance failed: " + completed.stderr
    return json.loads(completed.stdout)


def tree_bytes(repository):
    return {path.relative_to(repository).as_posix(): path.read_bytes()
            for path in repository.rglob("*") if path.is_file()}
