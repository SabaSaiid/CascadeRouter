"""Real HTTP chunking and peer identities exercise guards before scan/storage admission."""
import pytest
import os
from pathlib import Path

from acceptance_support import client_case, serve, tree_bytes
from backend.config import BackendConfig


@pytest.mark.parametrize("rate", [False, True])
def test_wire_boundary_rejections_do_not_read_targets_or_store_success(api_environment, tmp_path, monkeypatch, caplog, rate):
    previous, repository, directory = api_environment
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_bytes(b"PRIVATE_ACCEPTANCE_OUTSIDE_SOURCE\n")
    before = tree_bytes(repository), tree_bytes(outside)
    original_open = os.open
    def guarded_open(path, *args, **kwargs):
        if not isinstance(path, int) and Path(os.fsdecode(path)).name == "private.py":
            pytest.fail("Boundary opened the excluded test source")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded_open)
    settings = BackendConfig(permitted_repository_roots=previous.permitted_repository_roots, storage_directory=directory,
                             max_request_body_bytes=256, request_rate_limit=3 if rate else 60,
                             request_rate_window_seconds=3600)
    with serve(settings) as server:
        assert client_case(server.base, "http-boundaries.mjs", {"repository": str(repository), "outside": str(outside), "rate": rate}) == {"checked": True}
        with server.app.state.scan_service.storage._connection() as connection:
            for table in ("analyses", "jobs", "patches", "patch_validations"):
                assert connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    assert (tree_bytes(repository), tree_bytes(outside)) == before
    assert "PRIVATE_ACCEPTANCE" not in caplog.text and str(outside) not in caplog.text
