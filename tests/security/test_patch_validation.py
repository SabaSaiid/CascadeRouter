"""Security acceptance uses synthetic test evidence and guarded temporary roots."""

import ast
import builtins
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.config import BackendConfig
from backend.main import create_app
from backend.services import patches
from backend.services.errors import ServiceError
from backend.services.patches import PatchService


def trusted_test_service(sample, monkeypatch, revalidate=None):
    """Unit-only authority injection. No synthetic artifact is relabelled recorded."""
    proposal = sample.proposal(persist=True)
    service = sample.service
    service.optimizations = SimpleNamespace(revalidate=revalidate or (lambda record, check: check()))
    def subject(patch_id, check):
        assert patch_id == proposal.manifest.patch_id and proposal.manifest.provenance == "test"
        service.access.select(sample.analysis.repository_path)
        service.optimizations.revalidate(sample.record, check)
        return proposal, sample.analysis, sample.record
    monkeypatch.setattr(service, "_validation_subject", subject)
    return service, proposal


def report_count(env):
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        return connection.execute("SELECT COUNT(*) FROM patch_validations").fetchone()[0]


def test_validation_never_imports_executes_or_writes_target_and_persists_only_metadata(validation_environment, monkeypatch):
    env = validation_environment
    raw = (b'import target_never_import\nraise RuntimeError("PRIVATE_TARGET_MUST_NEVER_EXECUTE")\n'
           b'from openai import OpenAI\nclient = OpenAI()\n'
           b'response = client.chat.completions.create(model="local/baseline", messages=[])\n')
    sample = env.build_patch(raw)
    service, proposal = trusted_test_service(sample, monkeypatch)
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name in ("openai", "target_never_import"):
            pytest.fail("Validation imported a target dependency.")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(Path, "write_bytes", lambda *_args, **_kw: pytest.fail("Candidate/source bytes were written."))
    monkeypatch.setattr(Path, "write_text", lambda *_args, **_kw: pytest.fail("Candidate/source text was written."))
    report = service.validate(proposal.manifest.patch_id)
    assert report.result.status == "validated" and report.result.provenance == "test"
    assert env.storage.get_validation(report.validation_id) == report
    assert (env.repository / "app.py").read_bytes() == raw
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        payload = connection.execute("SELECT payload FROM patch_validations").fetchone()[0]
        assert b"PRIVATE_TARGET" not in payload and b"target_never_import" not in payload
        assert b"review_diff" not in payload and b"inode" not in payload


def test_second_source_pass_discards_earlier_candidate_success(validation_environment, monkeypatch):
    env = validation_environment
    sample = env.build_patch()
    service, proposal = trusted_test_service(sample, monkeypatch)
    original = patches.validate_file
    def changed(*args):
        outcome = original(*args)
        (env.repository / "app.py").write_bytes(sample.raw + b"# external change during validation\n")
        return outcome
    monkeypatch.setattr(patches, "validate_file", changed)
    report = service.validate(proposal.manifest.patch_id)
    assert report.result.status == "stale" and report.result.files == () and not report.result.complete
    assert env.storage.get_validation(report.validation_id) == report and report_count(env) == 1
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal


def test_cancelled_validation_persists_no_partial_success(validation_environment, monkeypatch):
    env = validation_environment
    sample = env.build_patch()
    service, proposal = trusted_test_service(sample, monkeypatch)
    cancellation = threading.Event()
    original = patches.validate_file
    def cancelled(*args):
        outcome = original(*args)
        cancellation.set()
        return outcome
    def check():
        if cancellation.is_set():
            raise ServiceError("capability_unavailable")
    monkeypatch.setattr(patches, "validate_file", cancelled)
    with pytest.raises(ServiceError) as error:
        service.validate(proposal.manifest.patch_id, check)
    assert error.value.code == "capability_unavailable" and report_count(env) == 0
    assert (env.repository / "app.py").read_bytes() == sample.raw


def test_revoked_approval_after_static_checks_cannot_issue_a_report(validation_environment, monkeypatch):
    env = validation_environment
    sample = env.build_patch()
    approvals = []
    def approval(record, check):
        assert record.response.result.provenance == "test"
        approvals.append(record.optimization_id)
        if len(approvals) == 2:
            raise ServiceError("capability_unavailable")
        check()
    service, proposal = trusted_test_service(sample, monkeypatch, approval)
    with pytest.raises(ServiceError) as error:
        service.validate(proposal.manifest.patch_id)
    assert error.value.code == "capability_unavailable" and len(approvals) == 2 and report_count(env) == 0
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal


def test_linked_source_directory_is_never_followed_by_validation(validation_environment, monkeypatch, tmp_path):
    env = validation_environment
    sample = env.build_patch()
    proposal = sample.proposal()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_bytes(b"PRIVATE_OUTSIDE_SOURCE\n")
    link = env.repository / "linked"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    original = os.open
    def guarded(path, *args, **kwargs):
        if Path(path).name == "private.py":
            pytest.fail("Validation opened a file outside its source manifest.")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded)
    try:
        result = sample.service._validate(proposal, sample.analysis, sample.manifest, sample.record)
        assert result.status == "stale" and result.files == ()
    finally:
        if os.name == "nt": link.rmdir()
        else: link.unlink()
    assert (outside / "private.py").read_bytes() == b"PRIVATE_OUTSIDE_SOURCE\n"


def test_failed_report_transaction_does_not_change_proposal_or_source(validation_environment, monkeypatch):
    env = validation_environment
    sample = env.build_patch()
    report = env.validation_report(sample)
    proposal = env.storage.get_patch(report.result.patch_id)
    original = env.storage._connection
    class Connection:
        def __init__(self, connection): self.connection = connection
        def execute(self, sql, *args):
            if sql.startswith("INSERT INTO patch_validations"):
                raise sqlite3.OperationalError("PRIVATE_WRITE_FAILURE")
            return self.connection.execute(sql, *args)
        def commit(self): return self.connection.commit()
    @contextmanager
    def failed():
        with original() as connection:
            yield Connection(connection)
    with monkeypatch.context() as scope:
        scope.setattr(env.storage, "_connection", failed)
        with pytest.raises(ServiceError) as error:
            env.storage.save_validation(report)
        assert error.value.code == "capability_unavailable"
    assert report_count(env) == 0 and env.storage.get_patch(proposal.manifest.patch_id) == proposal
    assert (env.repository / "app.py").read_bytes() == sample.raw


def test_new_endpoints_keep_origin_body_and_rate_boundaries(validation_environment, monkeypatch):
    env = validation_environment
    settings = BackendConfig(permitted_repository_roots=[env.repository], storage_directory=env.directory,
                             max_request_body_bytes=32, request_rate_limit=1)
    monkeypatch.setattr(PatchService, "validate", lambda *_: pytest.fail("Boundary rejection reached work."))
    monkeypatch.setattr(PatchService, "get_validation", lambda *_: pytest.fail("Rate rejection reached history."))
    path = "/api/patches/patch_" + "a" * 32 + "/validate"
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        assert client.post(path, headers={"Origin": "https://outside.invalid"}, json={}).status_code == 422
        assert client.post(path, content=b"x" * 33, headers={"Content-Type": "application/json"}).status_code == 413
        assert client.get("/api/patch-validations/validation_" + "a" * 64).status_code == 429


def test_unsupported_encoding_retains_precise_omission_and_no_syntax_claim(validation_environment):
    env = validation_environment
    raw = (b'# coding: latin-1\n# caf\xe9\nfrom openai import OpenAI\nclient = OpenAI()\n'
           b'response = client.chat.completions.create(model="local/baseline", messages=[])\n')
    report = env.validation_report(env.build_patch(raw))
    assert report.result.status == "unavailable" and report.result.files == ()
    assert report.result.omissions[0].reason == "unsupported_encoding" and not report.result.complete
    env.storage.save_validation(report)


def test_static_validation_modules_have_no_execution_or_provider_dispatch():
    root = Path(__file__).parents[2]
    for name in ("backend/compiler/patch_generator.py", "backend/compiler/patch_validator.py", "backend/services/patches.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"), feature_version=(3, 11))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not {name.split(".")[0] for name in names} & {
                    "subprocess", "importlib", "runpy", "py_compile", "socket", "requests", "httpx", "urllib", "openai", "nebius", "tavily"}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__", "open"}


def test_report_byte_limit_fails_without_replacing_proposal(validation_environment):
    from backend.services.storage import AnalysisStorage
    env = validation_environment
    sample = env.build_patch()
    report = env.validation_report(sample)
    proposal = env.storage.get_patch(report.result.patch_id)
    assert len(report.model_dump_json().encode("utf-8")) > 1024
    settings = BackendConfig(permitted_repository_roots=[env.repository], storage_directory=env.directory,
                             max_job_result_bytes=1024)
    limited = AnalysisStorage(settings)
    try:
        with pytest.raises(ServiceError) as error:
            limited.save_validation(report)
        assert error.value.code == "capacity_exceeded"
    finally:
        limited.close()
    assert report_count(env) == 0 and env.storage.get_patch(proposal.manifest.patch_id) == proposal
