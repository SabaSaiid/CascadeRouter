"""Temporary test datasets exercise approval, containment and substitution attacks."""

import hashlib
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas import AssetApproval, BenchmarkRegistryDocument, OfflineRecordingDocument
from backend.services.benchmark_assets import ApprovedAssetStore
from backend.services.benchmark_cases import BenchmarkRegistry, load_local_assets
from backend.services.errors import ServiceError
from backend.services.storage import AnalysisStorage


def test_explicit_test_approval_loads_versioned_assets_but_cannot_enable_production(asset_environment):
    env = asset_environment
    registry, executor = load_local_assets(env.settings, allow_test_assets=True)
    assert registry.document.origin == executor.provenance == "test"
    assert not registry.production_approved and not executor.production_approved
    assert registry.document.case_sets[0].content_digest is not None
    with pytest.raises(ServiceError):
        load_local_assets(env.settings)
    with pytest.raises(ServiceError):
        load_local_assets(env.configure(benchmark_approval_manifest_path=None), allow_test_assets=True)
    with pytest.raises(ServiceError):
        load_local_assets(env.configure(permitted_benchmark_data_roots=[]), allow_test_assets=True)


@pytest.mark.parametrize("path", ["../outside.json", "/absolute.json", r"C:\private.json", "a/../data.json", "a\\data.json"])
def test_manifest_traversal_and_absolute_paths_are_rejected(path):
    with pytest.raises(ValidationError):
        AssetApproval(asset_id="test", root_index=0, relative_path=path, kind="registry", provenance="test", digest="a" * 64)


def test_unapproved_path_is_rejected_before_opening_it(asset_environment, tmp_path, monkeypatch):
    env = asset_environment
    outside = tmp_path / "PRIVATE_UNAPPROVED.json"
    outside.write_text("PRIVATE_UNAPPROVED_DATA", encoding="utf-8")
    store = ApprovedAssetStore(env.settings, allow_test_assets=True)
    original = os.open
    def guarded(path, *args, **kwargs):
        if Path(path) == outside:
            pytest.fail("An unapproved asset was opened.")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded)
    with pytest.raises(ServiceError) as error:
        store.load(outside, "registry", 1024 * 1024)
    assert error.value.code == "repository_forbidden" and "PRIVATE" not in str(error.value)


def test_modified_missing_and_revoked_recordings_are_rejected(asset_environment):
    env = asset_environment
    registry, executor = load_local_assets(env.settings, allow_test_assets=True)
    plan = registry.resolve(env.request, env.analysis, env.settings, executor)
    original = env.recording_path.read_bytes()
    env.recording_path.write_bytes(original + b" ")
    with pytest.raises(ServiceError):
        executor.validate_plan(plan)
    env.recording_path.write_bytes(original)
    env.recording_path.unlink()
    with pytest.raises(ServiceError):
        executor.validate_plan(plan)
    env.recording_path.write_bytes(original)
    env.manifest_path.write_bytes(env.manifest_path.read_bytes() + b" ")
    with pytest.raises(ServiceError):
        executor.validate_plan(plan)


def test_declared_provenance_cannot_override_operator_pinned_bytes(asset_environment):
    env = asset_environment
    text = env.recording_path.read_text(encoding="utf-8")
    env.recording_path.write_text(text.replace('"provenance":"test"', '"provenance":"recorded"'), encoding="utf-8")
    with pytest.raises(ServiceError):
        load_local_assets(env.settings, allow_test_assets=True)


def test_file_replacement_before_open_is_detected_before_any_content_read(asset_environment, monkeypatch):
    env = asset_environment
    store = ApprovedAssetStore(env.settings, allow_test_assets=True)
    original_open, original_fdopen = os.open, os.fdopen
    holding = env.data_root / "original-registry.json"
    swapped = False
    attempted = False
    blocked = False
    def substitute(path, *args, **kwargs):
        nonlocal swapped, attempted, blocked
        if Path(path) == env.registry_path or str(path) == env.registry_path.name:
            attempted = True
            try:
                env.registry_path.rename(holding)
            except OSError as error:
                blocked = os.name == "nt" and getattr(error, "winerror", None) in (5, 32)
                raise
            env.registry_path.write_text("PRIVATE_SUBSTITUTE", encoding="utf-8")
            swapped = True
        return original_open(path, *args, **kwargs)
    class NoRead:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def fileno(self):
            return self.stream.fileno()
        def read(self, *args):
            pytest.fail("A substituted asset must be rejected before reading content.")
    monkeypatch.setattr(os, "open", substitute)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: NoRead(original_fdopen(*args, **kwargs)))
    try:
        with pytest.raises(ServiceError):
            store.load(env.registry_path, "registry", 1024 * 1024)
        assert attempted and (swapped or blocked)
    finally:
        if swapped:
            env.registry_path.unlink()
            holding.rename(env.registry_path)


def test_symbolic_link_asset_is_rejected(asset_environment, tmp_path):
    env = asset_environment
    store = ApprovedAssetStore(env.settings, allow_test_assets=True)
    outside = tmp_path / "outside.json"
    outside.write_text("PRIVATE_OUTSIDE", encoding="utf-8")
    holding = env.data_root / "original.json"
    env.registry_path.rename(holding)
    try:
        try:
            env.registry_path.symlink_to(outside)
        except OSError as error:
            pytest.skip(f"File symlink creation unavailable: errno={error.errno}, winerror={getattr(error, 'winerror', None)}")
        with pytest.raises(ServiceError):
            store.load(env.registry_path, "registry", 1024 * 1024)
    finally:
        if env.registry_path.is_symlink():
            env.registry_path.unlink()
        holding.rename(env.registry_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction data-root regression.")
def test_ancestor_junction_is_rejected_even_when_lexical_path_is_approved(asset_environment, tmp_path):
    import _winapi
    env = asset_environment
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "registry.json").write_bytes(env.registry_path.read_bytes())
    junction = env.data_root / "junction"
    _winapi.CreateJunction(str(outside), str(junction))
    try:
        from backend.schemas import BenchmarkApprovalManifest
        data = BenchmarkApprovalManifest.model_validate_json(env.manifest_path.read_bytes()).model_dump()
        data["assets"][0]["relative_path"] = "junction/registry.json"
        env.manifest_path.write_text(BenchmarkApprovalManifest.model_validate(data).model_dump_json(), encoding="utf-8")
        store = ApprovedAssetStore(env.settings, allow_test_assets=True)
        with pytest.raises(ServiceError):
            store.load(junction / "registry.json", "registry", 1024 * 1024)
    finally:
        junction.rmdir()  # Only this exact temporary junction, never its target.


def test_root_replacement_and_operator_manifest_placement_fail_closed(asset_environment):
    env = asset_environment
    store = ApprovedAssetStore(env.settings, allow_test_assets=True)
    parked = env.data_root.with_name("parked-data")
    env.data_root.rename(parked)
    env.data_root.mkdir()
    with pytest.raises(ServiceError):
        store.load(env.registry_path, "registry", 1024 * 1024)
    copied = env.data_root / "approvals.json"
    copied.write_bytes(env.manifest_path.read_bytes())
    with pytest.raises(ValidationError):
        env.configure(benchmark_registry_path=None, benchmark_recordings_path=None, benchmark_approval_manifest_path=copied)


@pytest.mark.parametrize("kind", ["case_sets", "evaluation_profiles"])
def test_version_catalog_is_immutable_across_restarts(offline_environment, kind):
    env = offline_environment
    env.storage.register_benchmark_versions(env.registry.version_records())
    data = env.registry.document.model_dump()
    original = getattr(env.registry.document, kind)[0]
    case_data = original.model_dump()
    if kind == "case_sets":
        case_data["cases"][0]["expected_output"] = "CHANGED_TEST_EXPECTATION"
    else:
        case_data["criteria_id"] = "changed-test-criteria"
    case_data["content_digest"] = None
    changed = env.pin(type(original).model_validate(case_data))
    data[kind] = [changed]
    modified = BenchmarkRegistry(BenchmarkRegistryDocument.model_validate(data))
    other = AnalysisStorage(env.settings)
    try:
        with pytest.raises(ServiceError) as error:
            other.register_benchmark_versions(modified.version_records())
        assert error.value.code == "source_conflict"
        bumped = env.pin(type(changed).model_validate({**changed.model_dump(), "version": "v2", "content_digest": None}))
        data[kind] = [bumped]
        other.register_benchmark_versions(BenchmarkRegistry(BenchmarkRegistryDocument.model_validate(data)).version_records())
    finally:
        other.close()


def test_record_and_output_digests_and_duplicate_ids_are_enforced(offline_environment):
    env = offline_environment
    for field, value in (("captured_output", "changed test output"), ("digest", "0" * 64)):
        data = env.document.model_dump()
        data["recordings"][0]["records"][0][field] = value
        with pytest.raises(ValidationError):
            OfflineRecordingDocument.model_validate(data)
    data = env.document.model_dump()
    data["recordings"][0]["records"] *= 2
    with pytest.raises(ValidationError):
        OfflineRecordingDocument.model_validate(data)


def test_oversized_and_duplicate_case_assets_are_rejected(offline_environment):
    env = offline_environment
    for change in (lambda data: data["case_sets"].extend(data["case_sets"]),
                   lambda data: data["case_sets"][0]["cases"].extend(data["case_sets"][0]["cases"] * 64),
                   lambda data: data["case_sets"][0]["cases"][0].update(input_text="x" * 8193)):
        data = env.registry.document.model_dump(mode="json")
        change(data)
        with pytest.raises(ValidationError):
            BenchmarkRegistryDocument.model_validate(data)
