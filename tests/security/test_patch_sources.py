"""Stale/replaced sources fail closed through the actual scanner boundary."""

import os
from pathlib import Path

import pytest

from backend.compiler import ast_scanner
from backend.schemas import PatchProposal
from backend.services.errors import ServiceError


def test_target_top_level_side_effects_and_missing_imports_are_never_executed(patch_environment):
    env = patch_environment
    raw = b'from pathlib import Path\nimport deliberately_uninstalled_target_package\nPath("PATCH_EXECUTION_MARKER").write_text("never")\nfrom openai import OpenAI\nclient=OpenAI()\nr=client.chat.completions.create(model="local/baseline", messages=[])\nraise RuntimeError("PRIVATE_TARGET_EXCEPTION")\n'
    before = {item.name for item in env.repository.iterdir()}
    # Opaque target side effects leave the graph incomplete and therefore
    # cannot produce a benchmark/optimization plan or an eligible patch.
    with pytest.raises(ServiceError) as error:
        env.build_patch(raw)
    assert error.value.code == "source_conflict"
    assert {item.name for item in env.repository.iterdir()} == before
    assert not (Path.cwd() / "PATCH_EXECUTION_MARKER").exists()
    assert (env.repository / "app.py").read_bytes() == raw


@pytest.mark.parametrize("path", ["../outside.py", "/absolute.py", "C:/outside.py", "nested/../../outside.py", "nested\\outside.py"])
def test_private_source_paths_cannot_traverse_or_use_host_paths(path):
    from pydantic import ValidationError
    from backend.schemas import SourceFileVersion
    with pytest.raises(ValidationError):
        SourceFileVersion(file_path=path, sha256="a" * 64, device=1, inode=1, size=1, mtime_ns=0, ctime_ns=0)


def test_private_capture_rejects_identity_changes_even_with_identical_hash(patch_environment):
    from backend.compiler.ast_scanner import _SourceVersion
    from backend.services.source_manifests import SourceCapture
    env = patch_environment
    capture = SourceCapture(env.repository)
    capture.observe(_SourceVersion("app.py", "a" * 64, 1, 2, 3, 4, 5))
    with pytest.raises(ServiceError) as error:
        capture.observe(_SourceVersion("app.py", "a" * 64, 1, 3, 3, 4, 5))
    assert error.value.code == "source_conflict"


@pytest.mark.parametrize("change", ["bytes", "identity", "missing", "new_python_file", "sdk_shadow"])
def test_stale_or_inconsistent_repository_cannot_generate_a_patch(patch_environment, change):
    env = patch_environment
    sample = env.build_patch()
    path = env.repository / "app.py"
    if change == "bytes":
        path.write_bytes(sample.raw + b"# changed source\n")
    elif change == "identity":
        path.rename(env.repository / "parked.txt")
        path.write_bytes(sample.raw)  # Identical content cannot hide a replaced file.
    elif change == "missing":
        path.unlink()
    elif change == "new_python_file":
        (env.repository / "new.py").write_text("value = 1\n", encoding="utf-8")
    else:
        (env.repository / "openai.py").write_text("raise RuntimeError('never executed')\n", encoding="utf-8")
    with pytest.raises(ServiceError) as error:
        sample.proposal()
    assert error.value.code == "source_conflict"


def test_change_during_transformation_is_rejected_by_second_guarded_pass(patch_environment, monkeypatch):
    from backend.services import patches
    env = patch_environment
    sample = env.build_patch()
    original = patches.generate_file
    def changed(*args):
        result = original(*args)
        (env.repository / "app.py").write_bytes(sample.raw + b"# changed after generation\n")
        return result
    monkeypatch.setattr(patches, "generate_file", changed)
    with pytest.raises(ServiceError):
        sample.proposal()
    with pytest.raises(ServiceError) as error:
        env.storage.get_patch("patch_" + "a" * 32)
    assert error.value.code == "not_found"


def test_source_symlink_is_not_followed(patch_environment, tmp_path):
    env = patch_environment
    sample = env.build_patch()
    path, outside = env.repository / "app.py", tmp_path / "outside.py"
    outside.write_text("PRIVATE_OUTSIDE_SOURCE\n", encoding="utf-8")
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"File symlink creation unavailable: errno={error.errno}, winerror={getattr(error, 'winerror', None)}")
    with pytest.raises(ServiceError):
        sample.proposal()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression.")
def test_source_directory_junction_cannot_escape_root(patch_environment, tmp_path):
    import _winapi
    env = patch_environment
    sample = env.build_patch()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("PRIVATE_OUTSIDE_SOURCE\n", encoding="utf-8")
    junction = env.repository / "linked"
    _winapi.CreateJunction(str(outside), str(junction))
    try:
        with pytest.raises(ServiceError):
            sample.proposal()
    finally:
        junction.rmdir()  # Remove this exact temporary junction only, never its target.


def test_file_replacement_before_open_cannot_read_substitute(patch_environment, monkeypatch):
    env = patch_environment
    sample = env.build_patch()
    path, holding = env.repository / "app.py", env.repository / "parked.txt"
    original, fdopen = os.open, os.fdopen
    attempted = swapped = blocked = False
    def replace(path_arg, *args, **kwargs):
        nonlocal attempted, swapped, blocked
        if str(path_arg) == path.name or Path(path_arg) == path:
            attempted = True
            try:
                path.rename(holding)
            except OSError as error:
                blocked = os.name == "nt" and getattr(error, "winerror", None) in (5, 32)
                raise
            path.write_text("PRIVATE_SUBSTITUTE", encoding="utf-8")
            swapped = True
        return original(path_arg, *args, **kwargs)
    class NoRead:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.stream.close()
        def fileno(self):
            return self.stream.fileno()
        def read(self, *_):
            pytest.fail("Substituted source was read before identity validation.")
    monkeypatch.setattr(os, "open", replace)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: NoRead(fdopen(*args, **kwargs)))
    try:
        with pytest.raises(ServiceError):
            sample.proposal()
        assert attempted and (swapped or blocked)
    finally:
        if swapped:
            path.unlink()
            holding.rename(path)


def test_replacement_between_scan_passes_is_prevented_or_rejected(patch_environment, monkeypatch):
    from backend.compiler import dag_builder
    from backend.services.scan_service import ScanService
    import asyncio
    import time
    env = patch_environment
    sample = env.build_patch()
    original = dag_builder.scan_repository
    blocked = False
    def replaced(*args, **kwargs):
        nonlocal blocked
        result = original(*args, **kwargs)
        path = env.repository / "app.py"
        try:
            path.rename(env.repository / "parked.txt")
        except OSError as error:
            if os.name != "nt" or getattr(error, "winerror", None) not in (5, 32):
                raise
            blocked = True  # The existing pinned directory prevents the race.
            return result
        path.write_bytes(sample.raw)
        return result
    monkeypatch.setattr(dag_builder, "scan_repository", replaced)
    scans = ScanService(env.settings)
    try:
        try:
            asyncio.run(scans.scan(str(env.repository), time.monotonic() + 20))
        except ServiceError as error:
            assert not blocked and error.code == "source_conflict"
        else:
            assert blocked and (env.repository / "app.py").read_bytes() == sample.raw
        assert ast_scanner._source_observer.get() is None
    finally:
        scans.close()


def test_oversized_review_diff_is_rejected(patch_environment, monkeypatch):
    from backend.services import patches
    env = patch_environment
    sample = env.build_patch()
    original = patches.assemble_proposal
    def limited(*args, **kwargs):
        return original(*args, **{**kwargs, "maximum": 1})
    monkeypatch.setattr(patches, "assemble_proposal", limited)
    with pytest.raises(ServiceError) as error:
        sample.proposal()
    assert error.value.code == "capacity_exceeded"


def test_arbitrary_model_change_cannot_be_persisted_as_approved_proposal(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    data = sample.proposal().model_dump(mode="json")
    data["manifest"]["files"][0]["edits"][0]["proposed_model_id"] = "unapproved/model"
    data.pop("digest")
    # Self-consistent hashes are not authorization to choose another model.
    import hashlib
    import json
    data["digest"] = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    proposal = PatchProposal.model_validate(data)
    with pytest.raises(ServiceError) as error:
        env.storage.save_patch(proposal)
    assert error.value.code == "source_conflict"
