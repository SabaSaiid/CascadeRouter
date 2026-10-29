"""Settings are explicit inputs; tests never read host environment values."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import BackendConfig, ConfigurationError


def test_defaults_are_local_bounded_and_fail_closed():
    config = BackendConfig()
    assert config.bind_host == "127.0.0.1" and config.bind_port == 8000
    assert config.scan_workers == 1 and config.job_workers == 2
    assert config.max_request_body_bytes == 1024 * 1024
    assert (config.request_rate_limit, config.request_rate_window_seconds, config.request_rate_max_clients) == (60, 60, 256)
    assert config.permitted_repository_roots == ()
    assert config.safe_report()["repository_scanning_configured"] is False
    with pytest.raises(ConfigurationError, match="explicit permitted-root policy"):
        config.require_repository_roots()


def test_explicit_root_injection_and_safe_reports(tmp_path):
    root = tmp_path / "PRIVATE_CONFIG_ROOT_NAME"
    root.mkdir()
    (root / ".env").write_text("SYNTHETIC_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
    config = BackendConfig(permitted_repository_roots=[str(root)], bind_port=8100)
    assert config.require_repository_roots() == (root.resolve(),)
    assert config.safe_report()["permitted_repository_root_count"] == 1
    assert config.safe_report()["repository_scanning_configured"] is True
    assert str(root) not in repr(config)
    assert "PRIVATE_CONFIG_ROOT_NAME" not in repr(config.safe_report())
    assert "PRIVATE_CONFIG_ROOT_NAME" not in config.model_dump_json()
    assert "permitted_repository_roots" not in config.model_dump()


def test_config_does_not_consult_environment_or_read_root_files(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()

    class ForbiddenEnvironment:
        def __getitem__(self, key):
            pytest.fail("Host environment values must not be accessed.")

        def get(self, key, default=None):
            pytest.fail("Host environment values must not be accessed.")

    def forbidden(*args, **kwargs):
        pytest.fail("Configuration must not read files or dotenv contents.")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "environ", ForbiddenEnvironment())
        scoped.setattr(os, "getenv", forbidden)
        scoped.setattr(Path, "open", forbidden)
        scoped.setattr(Path, "read_text", forbidden)
        scoped.setattr(Path, "read_bytes", forbidden)
        config = BackendConfig(permitted_repository_roots=[root])
        assert config.bind_host == "127.0.0.1"
        assert config.require_repository_roots() == (root,)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1"])
def test_numeric_loopback_bindings(host):
    assert BackendConfig(bind_host=host).bind_host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "example.invalid", "localhost", "::1%PRIVATE", 1, True])
def test_nonlocal_or_coerced_bindings_are_rejected(host):
    with pytest.raises(ValidationError):
        BackendConfig(bind_host=host)


@pytest.mark.parametrize("root_kind", ["relative", "missing", "file", "nul", "unc", "drive_root", "wrong_type"])
def test_invalid_roots_are_rejected_without_exposing_paths(tmp_path, root_kind):
    private = tmp_path / "PRIVATE_ROOT_PATH"
    if root_kind == "relative":
        value = "relative/repo"
    elif root_kind == "missing":
        value = private
    elif root_kind == "file":
        private.write_text("SYNTHETIC_PRIVATE_CONTENT", encoding="utf-8")
        value = private
    elif root_kind == "nul":
        value = str(private) + "\x00"
    elif root_kind == "unc":
        value = r"\\audit-invalid\share\repo"
    elif root_kind == "drive_root":
        value = Path(tmp_path.anchor)
    else:
        value = 42
    with pytest.raises(ValidationError) as error:
        BackendConfig(permitted_repository_roots=[value])
    assert "PRIVATE_ROOT_PATH" not in str(error.value)
    assert "SYNTHETIC_PRIVATE_CONTENT" not in str(error.value)


@pytest.mark.parametrize("roots", ["repo", None, {"root": "repo"}, ["repo"] * 17])
def test_root_policy_requires_a_bounded_explicit_array(roots):
    with pytest.raises(ValidationError):
        BackendConfig(permitted_repository_roots=roots)


def test_duplicate_roots_are_rejected(tmp_path):
    with pytest.raises(ValidationError, match="duplicated"):
        BackendConfig(permitted_repository_roots=[tmp_path, str(tmp_path)])


def test_parent_alias_cannot_authorize_an_entire_filesystem(tmp_path):
    alias = tmp_path.joinpath(*(".." for _ in tmp_path.parts[1:]))
    assert alias != Path(tmp_path.anchor)
    assert alias.resolve() == Path(tmp_path.anchor)
    with pytest.raises(ValidationError):
        BackendConfig(permitted_repository_roots=[alias])


def test_unreadable_root_metadata_error_is_sanitized(tmp_path, monkeypatch):
    original = Path.lstat

    def denied(path, *args, **kwargs):
        if path == tmp_path:
            raise PermissionError("PRIVATE_PERMISSION_ERROR")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(ValidationError) as error:
        BackendConfig(permitted_repository_roots=[tmp_path])
    assert "PRIVATE_PERMISSION_ERROR" not in str(error.value)


def test_opening_directory_does_not_enumerate_contents(tmp_path, monkeypatch):
    opened = []

    class DirectoryHandle:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            pytest.fail("Root validation must not enumerate directory contents.")

    def open_directory(path):
        opened.append(path)
        return DirectoryHandle()

    monkeypatch.setattr(os, "scandir", open_directory)
    BackendConfig(permitted_repository_roots=[tmp_path])
    assert opened == [tmp_path.resolve()]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression.")
def test_config_rejects_final_directory_junctions(tmp_path):
    import _winapi

    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "junction"
    _winapi.CreateJunction(str(target), str(junction))
    try:
        with pytest.raises(ValidationError):
            BackendConfig(permitted_repository_roots=[junction])
    finally:
        junction.rmdir()  # Remove only the temporary junction, never its target.


@pytest.mark.parametrize("field,maximum", [
    ("bind_port", 65535), ("max_request_body_bytes", 16 * 1024 * 1024),
    ("request_rate_limit", 10000), ("request_rate_window_seconds", 3600), ("request_rate_max_clients", 4096),
    ("scan_workers", 4), ("job_workers", 8), ("max_queued_jobs", 256),
    ("max_jobs", 2048), ("max_concurrent_provider_requests", 16),
    ("max_requests_per_job", 1024), ("max_output_tokens", 8192),
    ("max_provider_response_bytes", 8 * 1024 * 1024), ("scan_timeout_seconds", 120),
    ("provider_timeout_seconds", 120), ("job_timeout_seconds", 1800),
    ("job_retention_seconds", 604800),
])
@pytest.mark.parametrize("invalid", ["zero", "negative", "boolean", "string", "fraction", "oversized"])
def test_resource_limits_are_positive_strict_and_bounded(field, maximum, invalid):
    value = {"zero": 0, "negative": -1, "boolean": True, "string": "2", "fraction": 1.5,
             "oversized": maximum + 1}[invalid]
    with pytest.raises(ValidationError):
        BackendConfig(**{field: value})


def test_consistent_limit_boundaries_and_freezing():
    config = BackendConfig(max_jobs=256, max_queued_jobs=256, job_workers=8,
                           provider_timeout_seconds=120, job_timeout_seconds=120)
    assert config.max_queued_jobs == 256
    with pytest.raises(ValidationError):
        BackendConfig(max_jobs=1)
    with pytest.raises(ValidationError):
        BackendConfig(job_timeout_seconds=1)
    with pytest.raises(ValidationError):
        config.bind_port = 9000


@pytest.mark.parametrize("field", ["api_key", "provider_token", "dotenv_path", "secret", "command"])
def test_credentials_and_unexpected_settings_are_rejected_and_hidden(field):
    private = "PRIVATE_CONFIGURATION_SECRET"
    with pytest.raises(ValidationError) as error:
        BackendConfig(**{field: private})
    assert private not in str(error.value)


def test_configuration_does_not_claim_time_of_use_authorization(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    config = BackendConfig(permitted_repository_roots=[root])
    root.rmdir()
    # The policy remains a configuration snapshot. Future services must recheck
    # root existence, identity and containment; this method does not authorize paths.
    assert config.require_repository_roots() == (root,)
