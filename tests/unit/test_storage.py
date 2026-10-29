"""SQLite integrity, bounded state and immutable public snapshots."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.config import BackendConfig
from backend.services.compiler_adapter import analyze_for_api
from backend.services.errors import ServiceError
from backend.services.storage import AnalysisStorage


def snapshot(repository, index=1):
    return analyze_for_api(str(repository), analysis_id="analysis_" + f"{index:032x}", timestamp=datetime.now(timezone.utc))


def test_storage_round_trip_duplicate_immutability_and_restart(api_environment):
    settings, repository, directory = api_environment
    storage = AnalysisStorage(settings)
    response = snapshot(repository)
    encoded = storage.save(response)
    assert encoded == response.model_dump_json().encode("utf-8")
    assert storage.get(response.analysis_id) == response
    with pytest.raises(ServiceError) as error:
        storage.save(response)
    assert error.value.code == "source_conflict"
    with sqlite3.connect(directory / "analyses.sqlite3") as connection:
        for statement in ("UPDATE analyses SET completion_status = 'changed'", "DELETE FROM analyses"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement)
    storage.close()
    reopened = AnalysisStorage(settings)
    assert reopened.get(response.analysis_id) == response
    with pytest.raises(ServiceError) as error:
        reopened.get("analysis_" + "0" * 32)
    assert error.value.code == "not_found"
    reopened.close()


def test_concurrent_transactional_insert_and_same_id_race(api_environment):
    settings, repository, _ = api_environment
    storage = AnalysisStorage(settings)
    responses = [snapshot(repository, index) for index in range(1, 9)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert len(list(executor.map(storage.save, responses))) == 8
        assert list(executor.map(storage.get, [response.analysis_id for response in responses])) == responses
        duplicate = snapshot(repository, 10)

        def insert(_):
            try:
                storage.save(duplicate)
                return "saved"
            except ServiceError as error:
                return error.code

        results = list(executor.map(insert, range(4)))
    assert results.count("saved") == 1 and results.count("source_conflict") == 3
    storage.close()


def test_record_cap_and_closed_store_fail_safely(api_environment):
    settings, repository, directory = api_environment
    settings = BackendConfig(permitted_repository_roots=settings.permitted_repository_roots,
                             storage_directory=directory, max_stored_analyses=1)
    storage = AnalysisStorage(settings)
    storage.save(snapshot(repository))
    with pytest.raises(ServiceError) as error:
        storage.save(snapshot(repository, 2))
    assert error.value.code == "capacity_exceeded"
    storage.close()
    with pytest.raises(ServiceError) as error:
        storage.get("analysis_" + "1" * 32)
    assert error.value.code == "capability_unavailable"


@pytest.mark.parametrize("kind", ["version", "unversioned_table", "garbage", "sqlite_prefix"])
def test_incompatible_storage_is_not_replaced(api_environment, kind):
    settings, _, directory = api_environment
    path = directory / "analyses.sqlite3"
    if kind == "garbage":
        path.write_bytes(b"PRIVATE_INVALID_DATABASE")
    else:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE sqliteXprivate (value TEXT)" if kind == "sqlite_prefix" else "CREATE TABLE private_table (value TEXT)")
            if kind == "version":
                connection.execute("PRAGMA user_version = 99")
    before = path.read_bytes()
    with pytest.raises(ServiceError) as error:
        AnalysisStorage(settings)
    assert error.value.code == "capability_unavailable" and "PRIVATE" not in str(error.value)
    assert path.read_bytes() == before


def test_storage_must_be_explicit_and_outside_all_scan_roots(api_environment):
    settings, repository, _ = api_environment
    with pytest.raises(ValidationError):
        BackendConfig(permitted_repository_roots=settings.permitted_repository_roots, storage_directory=repository)
    assert BackendConfig().storage_directory is None
    with pytest.raises(ServiceError):
        AnalysisStorage(BackendConfig())


def test_storage_paths_hidden_and_limits_strict(api_environment):
    settings, _, directory = api_environment
    assert str(directory) not in repr(settings) and str(directory) not in str(settings.safe_report())
    for changes in ({"max_stored_analyses": True}, {"max_stored_analyses": 4097},
                    {"max_stored_analysis_bytes": 1023}, {"max_stored_analysis_bytes": 64 * 1024 * 1024 + 1}):
        with pytest.raises(ValidationError):
            BackendConfig(**changes)


def test_payload_bound_and_parameterized_lookup(api_environment):
    settings, repository, directory = api_environment
    limited = BackendConfig(permitted_repository_roots=settings.permitted_repository_roots,
                            storage_directory=directory, max_stored_analysis_bytes=1024)
    storage = AnalysisStorage(limited)
    with pytest.raises(ServiceError) as error:
        storage.save(snapshot(repository))
    assert error.value.code == "capacity_exceeded"
    with pytest.raises(ServiceError) as error:
        storage.get("' OR 1=1; DROP TABLE analyses; --")
    assert error.value.code == "not_found"
    storage.close()


def test_tampered_snapshot_metadata_is_not_returned(api_environment):
    settings, repository, directory = api_environment
    storage = AnalysisStorage(settings)
    response = snapshot(repository)
    storage.save(response)
    # Simulate an operator changing the on-disk state, then restoring its schema.
    from backend.services.storage import _DDL
    with sqlite3.connect(directory / "analyses.sqlite3") as connection:
        connection.execute("DROP TRIGGER immutable_update")
        connection.execute("UPDATE analyses SET schema_version = ?", ("unrecognized",))
        connection.execute(_DDL[1])
    with pytest.raises(ServiceError) as error:
        storage.get(response.analysis_id)
    assert error.value.code == "source_conflict"
    storage.close()
