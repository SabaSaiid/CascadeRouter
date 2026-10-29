"""Real loopback transport integration, with target bytes checked before/after."""
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from backend.config import BackendConfig
from acceptance_support import client_case, node24, serve, tree_bytes


def test_typescript_client_against_real_local_backend(tmp_path):
    node = node24()
    repository = tmp_path / "repository"
    storage = tmp_path / "storage"
    repository.mkdir()
    storage.mkdir()
    # Importing or executing this target would fail. It is only parsed by the scanner.
    source = repository / "app.py"
    original = b'raise RuntimeError("TARGET_MUST_NEVER_EXECUTE")\nfrom openai import OpenAI\nclient = OpenAI()\nresponse = client.chat.completions.create(model="local/baseline", messages=[])\n'
    source.write_bytes(original)
    settings = BackendConfig(permitted_repository_roots=[repository], storage_directory=storage)
    with serve(settings) as server:
        script = Path(__file__).resolve().parents[2] / "frontend/tests/live-backend.mjs"
        completed = subprocess.run([node, str(script), server.base, str(repository)], capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, "Local TypeScript contract integration failed: " + completed.stderr
        assert "Real local backend:" in completed.stdout
    assert source.read_bytes() == original
    assert sorted(path.name for path in repository.iterdir()) == ["app.py"]


@pytest.mark.parametrize("partial", [False, True])
def test_client_scan_graph_and_partial_coverage_survive_storage_restart(api_environment, partial):
    from backend.services.storage import AnalysisStorage
    from backend.services.errors import ServiceError
    settings, repository, _ = api_environment
    # This tripwire is part of static input, never a command to run.
    source = repository / "app.py"
    source.write_bytes(b'assert False, "TARGET_MUST_NEVER_EXECUTE"\n' + source.read_bytes().replace(b"model=MODEL", b'model="local/candidate"'))
    if partial:
        (repository / "invalid.py").write_bytes(b"def broken(:\n")
    before = tree_bytes(repository)
    with serve(settings) as server:
        value = client_case(server.base, "scan.mjs", {"repository": str(repository), "partial": partial})
        stored = server.app.state.scan_service.storage.get(value["analysis_id"])
        assert stored.model_dump(mode="json") == value
    with closing(AnalysisStorage(settings)) as storage:
        assert storage.get(value["analysis_id"]) == stored
        if partial:
            with pytest.raises(ServiceError) as error:
                storage.get_source_manifest(stored.analysis_id)
            assert error.value.code == "source_evidence_unavailable"
        else:
            assert storage.get_source_manifest(stored.analysis_id).complete
    assert tree_bytes(repository) == before
