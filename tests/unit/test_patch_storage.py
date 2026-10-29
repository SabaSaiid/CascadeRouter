"""Private scan evidence and immutable content-addressed artifact persistence."""

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from backend.schemas import PatchProposal, PrivateSourceManifest, ScanResponse, content_digest
from backend.services.errors import ServiceError
from backend.services.storage import AnalysisStorage, _DDL_V3


def test_source_manifest_is_private_bound_to_scan_and_retained_across_restart(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    assert sample.manifest.complete and sample.manifest.digest is not None
    assert sample.manifest.files[0].size == len(sample.raw)
    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, (tuple, list)):
            return set().union(*(keys(item) for item in value))
        return set()
    assert not keys(sample.analysis.model_dump()) & {"root_inode", "source_manifest", "sha256", "mtime_ns", "fingerprint"}
    other = AnalysisStorage(env.settings)
    try:
        assert other.get_source_manifest(sample.analysis.analysis_id) == sample.manifest
    finally:
        other.close()


def test_historical_analysis_is_not_backfilled_from_current_source(patch_environment):
    env = patch_environment
    historical = env.analysis
    with pytest.raises(ServiceError) as error:
        env.storage.get_source_manifest(historical.analysis_id)
    assert error.value.code == "source_evidence_unavailable"
    env.build_patch()
    with pytest.raises(ServiceError) as error:
        env.storage.get_source_manifest(historical.analysis_id)
    assert error.value.code == "source_evidence_unavailable"


def test_optimization_and_patch_round_trip_and_duplicate_ids_cannot_overwrite(patch_environment):
    env = patch_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal
    assert env.storage.save_optimization(sample.record.response) == sample.record.response
    with pytest.raises(ServiceError) as error:
        env.storage.save_patch(proposal)
    assert error.value.code == "source_conflict"
    other = AnalysisStorage(env.settings)
    try:
        assert other.get_patch(proposal.manifest.patch_id) == proposal
        assert other.get_optimization(sample.record.optimization_id) == sample.record
    finally:
        other.close()


@pytest.mark.parametrize("table", ["source_manifests", "optimizations", "patches"])
def test_sql_update_and_delete_are_rejected_for_immutable_artifacts(patch_environment, table):
    env = patch_environment
    sample = env.build_patch()
    sample.proposal(persist=True)
    # Table names are a fixed test allowlist, never a client-supplied query.
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        for statement in (f"UPDATE {table} SET payload = ?", f"DELETE FROM {table}"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, (b"changed",) if "UPDATE" in statement else ())


@pytest.mark.parametrize("table,key", [("source_manifests", "analysis_id"), ("optimizations", "optimization_id"), ("patches", "patch_id")])
def test_corrupt_artifact_payload_is_rejected_before_retrieval(patch_environment, table, key):
    env = patch_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    identifiers = {"analysis_id": sample.analysis.analysis_id, "optimization_id": sample.record.optimization_id,
                   "patch_id": proposal.manifest.patch_id}
    triggers = {"source_manifests": "immutable_source_update", "optimizations": "immutable_optimization_update", "patches": "immutable_patch_update"}
    getter = {"source_manifests": env.storage.get_source_manifest, "optimizations": env.storage.get_optimization, "patches": env.storage.get_patch}[table]
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        sql = connection.execute("SELECT sql FROM sqlite_master WHERE name = ?", (triggers[table],)).fetchone()[0]
        connection.execute("DROP TRIGGER " + triggers[table])
        connection.execute(f"UPDATE {table} SET payload = ? WHERE {key} = ?", (b'{"PRIVATE_CORRUPT":true}', identifiers[key]))
        connection.execute(sql)
    with pytest.raises(ServiceError) as error:
        getter(identifiers[key])
    assert error.value.code == "source_conflict" and "PRIVATE" not in str(error.value)


def test_manifest_and_scan_insert_rollback_together(patch_environment, monkeypatch):
    env = patch_environment
    sample = env.build_patch()
    response = ScanResponse.model_validate({**sample.analysis.model_dump(), "analysis_id": "analysis_" + "f" * 32})
    data = {**sample.manifest.model_dump(), "analysis_id": response.analysis_id,
            "analysis_digest": hashlib.sha256(response.model_dump_json().encode()).hexdigest(), "digest": None}
    manifest = PrivateSourceManifest.model_validate(data)
    manifest = PrivateSourceManifest.model_validate({**manifest.model_dump(), "digest": content_digest(manifest, exclude={"digest"})})
    original = env.storage._connection
    class Connection:
        def __init__(self, connection):
            self.connection = connection
        def execute(self, sql, *args):
            if sql.startswith("INSERT INTO source_manifests"):
                raise sqlite3.OperationalError("PRIVATE_SIMULATED_WRITE_FAILURE")
            return self.connection.execute(sql, *args)
        def commit(self):
            return self.connection.commit()
    @contextmanager
    def failing():
        with original() as connection:
            yield Connection(connection)
    with monkeypatch.context() as scope:
        scope.setattr(env.storage, "_connection", failing)
        with pytest.raises(ServiceError):
            env.storage.save(response, source_manifest=manifest)
    with pytest.raises(ServiceError) as error:
        env.storage.get(response.analysis_id)
    assert error.value.code == "not_found"


def test_v3_migration_preserves_legacy_records_without_inventing_manifests(api_environment):
    from backend.services.compiler_adapter import analyze_for_api
    settings, repository, directory = api_environment
    historical = analyze_for_api(str(repository), analysis_id="analysis_" + "b" * 32, timestamp=datetime.now(timezone.utc))
    with sqlite3.connect(directory / "analyses.sqlite3") as connection:
        for statement in _DDL_V3:
            connection.execute(statement)
        connection.execute("INSERT INTO analyses (analysis_id, created_at, schema_version, completion_status, payload) VALUES (?, ?, ?, ?, ?)",
                           (historical.analysis_id, historical.model_dump(mode="json")["timestamp"], historical.schema_version,
                            "complete", historical.model_dump_json().encode("utf-8")))
        connection.execute("PRAGMA user_version = 3")
    storage = AnalysisStorage(settings)
    try:
        with sqlite3.connect(directory / "analyses.sqlite3") as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
            assert connection.execute("SELECT COUNT(*) FROM source_manifests").fetchone()[0] == 0
        assert storage.get(historical.analysis_id) == historical
        with pytest.raises(ServiceError) as error:
            storage.get_source_manifest(historical.analysis_id)
        assert error.value.code == "source_evidence_unavailable"
    finally:
        storage.close()


def test_valid_json_with_changed_review_bytes_fails_its_artifact_digest(patch_environment):
    import json
    env = patch_environment
    proposal = env.build_patch().proposal(persist=True)
    data = proposal.model_dump(mode="json")
    data["review_diff"] += "PRIVATE_TAMPER"
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'immutable_patch_update'").fetchone()[0]
        connection.execute("DROP TRIGGER immutable_patch_update")
        connection.execute("UPDATE patches SET payload = ? WHERE patch_id = ?",
                           (json.dumps(data).encode(), proposal.manifest.patch_id))
        connection.execute(trigger)
    with pytest.raises(ServiceError) as error:
        env.storage.get_patch(proposal.manifest.patch_id)
    assert error.value.code == "source_conflict" and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("column,value", [
    ("patch_id", "patch_" + "b" * 32),
    ("analysis_id", "analysis_" + "b" * 32),
    ("optimization_id", "opt_" + "b" * 64),
    ("digest", "b" * 64),
])
def test_valid_patch_payload_cannot_hide_corrupt_storage_identity(patch_environment, column, value):
    env = patch_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    identifier = value if column == "patch_id" else proposal.manifest.patch_id
    # Simulate storage corruption, restoring the immutable trigger immediately.
    # The column is from the fixed parametrization, never caller-controlled SQL.
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        original = connection.execute("SELECT payload FROM patches WHERE patch_id = ?", (proposal.manifest.patch_id,)).fetchone()[0]
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'immutable_patch_update'").fetchone()[0]
        connection.execute("DROP TRIGGER immutable_patch_update")
        connection.execute(f"UPDATE patches SET {column} = ? WHERE patch_id = ?", (value, proposal.manifest.patch_id))
        connection.execute(trigger)
        retained = connection.execute("SELECT payload FROM patches WHERE patch_id = ?", (identifier,)).fetchone()[0]
        assert retained == original and PatchProposal.model_validate_json(retained) == proposal

    assert proposal.manifest.provenance == "test"
    restarted = AnalysisStorage(env.settings)
    try:
        for storage in (env.storage, restarted):
            with pytest.raises(ServiceError) as error:
                storage.get_patch(identifier)
            assert error.value.code == "source_conflict"
        assert restarted.get_source_manifest(sample.analysis.analysis_id) == sample.manifest
        assert restarted.get_optimization(sample.record.optimization_id) == sample.record
        assert (env.repository / "app.py").read_bytes() == sample.raw
    finally:
        restarted.close()
