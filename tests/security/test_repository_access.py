"""Authorization attacks use temporary trees only; target Python is never run."""

import os
from pathlib import Path

import pytest

from backend.compiler import ast_scanner, dag_builder
from backend.config import BackendConfig, ConfigurationError
from backend.services.errors import ServiceError
from backend.services.repository_access import RepositoryAccess


def test_explicit_relative_resolution_and_absolute_canonical_path(api_environment, monkeypatch):
    settings, repository, storage = api_environment
    access = RepositoryAccess(settings)
    monkeypatch.chdir(storage)
    for requested in ("repository", str(repository)):
        with access.authorize(requested) as approved:
            assert approved == repository.resolve()


@pytest.mark.parametrize("requested", ["../outside", "repository/../../outside", r"repository\..\outside",
                                         r"\\invalid\share\repo", r"\\?\C:\repo", "C:relative", "/".join(["child"] * 65)])
def test_forbidden_paths_rejected_before_filesystem_access(api_environment, monkeypatch, requested):
    settings, _, _ = api_environment
    access = RepositoryAccess(settings)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected path must not be resolved or inspected.")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    with pytest.raises(ServiceError) as error:
        with access.authorize(requested):
            pytest.fail("Forbidden path authorized.")
    assert error.value.code == "repository_forbidden"


def test_outside_missing_and_file_paths_have_distinct_safe_failures(api_environment):
    settings, repository, storage = api_environment
    access = RepositoryAccess(settings)
    for requested, code in ((str(storage), "repository_forbidden"), ("missing", "repository_unavailable"),
                            ("repository/app.py", "repository_unavailable")):
        with pytest.raises(ServiceError) as error:
            with access.authorize(requested):
                pytest.fail("Invalid path authorized.")
        assert error.value.code == code
        assert str(repository.parent) not in str(error.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows normalization and alternate-stream path policy.")
@pytest.mark.parametrize("requested", ["repository/.. ", "repository.", "repository ", "repository:stream"])
def test_windows_ambiguous_components_are_rejected_without_access(api_environment, monkeypatch, requested):
    access = RepositoryAccess(api_environment[0])

    def forbidden(*args, **kwargs):
        pytest.fail("Ambiguous Windows paths must be rejected before filesystem access.")

    monkeypatch.setattr(Path, "lstat", forbidden)
    with pytest.raises(ServiceError) as error:
        with access.authorize(requested):
            pytest.fail("Ambiguous path authorized.")
    assert error.value.code == "repository_forbidden"


def test_empty_policy_and_ambiguous_relative_paths_fail_closed(api_environment):
    settings, _, storage = api_environment
    with pytest.raises(ConfigurationError):
        RepositoryAccess(BackendConfig())
    multiple = BackendConfig(permitted_repository_roots=[*settings.permitted_repository_roots, storage])
    with pytest.raises(ServiceError) as error:
        RepositoryAccess(multiple).select("repository")
    assert error.value.code == "invalid_request"


def test_root_identity_change_after_initialization_is_detected(api_environment):
    settings, repository, _ = api_environment
    access = RepositoryAccess(settings)
    root = repository.parent
    parked = root.with_name("parked")
    root.rename(parked)
    root.mkdir()
    (root / "repository").mkdir()
    with pytest.raises(ServiceError) as error:
        with access.authorize("repository"):
            pytest.fail("Changed trusted root authorized.")
    assert error.value.code == "source_conflict"


def test_final_symlink_escape_is_rejected(api_environment):
    settings, repository, storage = api_environment
    link = repository.parent / "escape"
    try:
        link.symlink_to(storage, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlink creation unavailable: errno={error.errno}, winerror={getattr(error, 'winerror', None)}")
    try:
        with pytest.raises(ServiceError) as error:
            with RepositoryAccess(settings).authorize("escape"):
                pytest.fail("Symlink authorized.")
        assert error.value.code == "repository_forbidden"
    finally:
        link.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction authorization regression.")
@pytest.mark.parametrize("suffix", ["", "/child"])
def test_junction_and_ancestor_junction_escape_rejected(api_environment, suffix):
    import _winapi

    settings, repository, storage = api_environment
    (storage / "child").mkdir()
    junction = repository.parent / "escape"
    _winapi.CreateJunction(str(storage), str(junction))
    try:
        with pytest.raises(ServiceError) as error:
            with RepositoryAccess(settings).authorize("escape" + suffix):
                pytest.fail("Junction escape authorized.")
        assert error.value.code == "repository_forbidden"
    finally:
        junction.rmdir()  # Only this exact temporary junction, never its target.


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-lock regression.")
def test_windows_outer_guards_prevent_root_and_ancestor_replacement(api_environment):
    settings, repository, _ = api_environment
    access = RepositoryAccess(settings)
    with access.authorize("repository"):
        for path in (repository.parent, repository):
            with pytest.raises(OSError):
                path.rename(path.with_name("swapped"))
        result = dag_builder.analyze_repository(str(repository))
        assert len(result.scan_result.nodes) == 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX namespace replacement; Windows pins prevent this rename.")
@pytest.mark.parametrize("when", ["before_scan", "before_graph"])
def test_posix_replacement_cannot_read_replacement_sources(api_environment, monkeypatch, when):
    settings, repository, _ = api_environment
    access = RepositoryAccess(settings)
    original = dag_builder.scan_repository
    replacement = repository.with_name("original")

    def swap():
        repository.rename(replacement)
        repository.mkdir()
        (repository / "PRIVATE_REPLACEMENT.py").write_text("raise RuntimeError('never read')", encoding="utf-8")

    def scan(path, **kwargs):
        result = original(path, **kwargs)
        swap()
        return result

    if when == "before_graph":
        monkeypatch.setattr(dag_builder, "scan_repository", scan)
    opened = []
    original_scan_file = ast_scanner._RepositoryScan.scan_file

    def read(self, path, *args, **kwargs):
        opened.append(path.name)
        return original_scan_file(self, path, *args, **kwargs)

    monkeypatch.setattr(ast_scanner._RepositoryScan, "scan_file", read)
    with pytest.raises(ServiceError) as error:
        with access.authorize("repository"):
            if when == "before_scan":
                swap()
            dag_builder.analyze_repository(str(repository))
    assert error.value.code == "source_conflict"
    assert "PRIVATE_REPLACEMENT.py" not in opened


def test_scoped_compiler_identity_guard_covers_both_reads_and_resets(api_environment, monkeypatch):
    settings, repository, _ = api_environment
    seen = []
    original = ast_scanner._RepositoryScan.run

    def run(self):
        seen.append(ast_scanner._expected_repository.get())
        return original(self)

    monkeypatch.setattr(ast_scanner._RepositoryScan, "run", run)
    with RepositoryAccess(settings).authorize("repository"):
        dag_builder.analyze_repository(str(repository))
    assert len(seen) == 2 and all(item is not None and item[0] == repository for item in seen)
    assert ast_scanner._expected_repository.get() is None
    dag_builder.analyze_repository(str(repository))
    assert seen[-2:] == [None, None]
