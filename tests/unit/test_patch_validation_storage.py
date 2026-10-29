"""Immutable static observations reuse the guarded SQLite artifact store."""

import sqlite3

import pytest

from backend.schemas import PatchValidationReport
from backend.services.errors import ServiceError
from backend.services.storage import AnalysisStorage


def test_validation_round_trip_restart_and_identical_observation_are_idempotent(validation_environment):
    env = validation_environment
    sample = env.build_patch()
    report = env.validation_report(sample)
    proposal = env.storage.get_patch(report.result.patch_id)
    assert env.storage.save_validation(report) == env.storage.save_validation(report) == report
    restarted = AnalysisStorage(env.settings)
    try:
        assert restarted.get_validation(report.validation_id) == report
        assert restarted.get_patch(report.result.patch_id) == proposal
        assert restarted.get_source_manifest(sample.analysis.analysis_id) == sample.manifest
    finally:
        restarted.close()
    assert (env.repository / "app.py").read_bytes() == sample.raw


def test_validation_records_cannot_be_updated_or_deleted(validation_environment):
    env = validation_environment
    report = env.validation_report(env.build_patch())
    env.storage.save_validation(report)
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        for statement in ("UPDATE patch_validations SET digest = 'changed'", "DELETE FROM patch_validations"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)


@pytest.mark.parametrize("column,value", [
    ("validation_id", "validation_" + "b" * 64), ("patch_id", "patch_" + "b" * 32),
    ("analysis_id", "analysis_" + "b" * 32), ("proposal_digest", "b" * 64),
    ("source_manifest_digest", "b" * 64), ("digest", "b" * 64), ("payload", b'{"PRIVATE":true}'),
])
def test_corrupt_validation_identity_or_payload_fails_closed(validation_environment, column, value):
    env = validation_environment
    report = env.validation_report(env.build_patch())
    env.storage.save_validation(report)
    identifier = value if column == "validation_id" else report.validation_id
    # Fixed test columns simulate corruption; the immutable trigger is restored.
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'immutable_validation_update'").fetchone()[0]
        connection.execute("DROP TRIGGER immutable_validation_update")
        connection.execute(f"UPDATE patch_validations SET {column} = ?", (value,))
        connection.execute(trigger)
    with pytest.raises(ServiceError) as error:
        env.storage.get_validation(identifier)
    assert error.value.code == "source_conflict" and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("field,value", [("proposal_digest", "b" * 64), ("analysis_id", "analysis_" + "b" * 32),
                                       ("source_manifest_digest", "b" * 64)])
def test_rehashed_report_with_wrong_subject_is_rejected_without_insertion(validation_environment, field, value):
    env = validation_environment
    report = env.validation_report(env.build_patch())
    forged = PatchValidationReport.create(result={**report.result.model_dump(), field: value},
        checked_at=report.checked_at, python_version=report.python_version)
    with pytest.raises(ServiceError) as error:
        env.storage.save_validation(forged)
    assert error.value.code == "source_conflict"
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM patch_validations").fetchone()[0] == 0


def test_report_capacity_does_not_replace_an_existing_observation(validation_environment):
    env = validation_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    first = env.validation_report(sample, proposal)
    second = env.validation_report(sample, proposal, checked_at="2026-10-30T00:00:00Z")
    env.storage.max_jobs = 1
    env.storage.save_validation(first)
    assert env.storage.save_validation(first) == first
    with pytest.raises(ServiceError) as error:
        env.storage.save_validation(second)
    assert error.value.code == "capacity_exceeded" and env.storage.get_validation(first.validation_id) == first


def test_v4_migration_preserves_proposals_without_backfilling_reports(validation_environment):
    env = validation_environment
    sample = env.build_patch()
    proposal = sample.proposal(persist=True)
    env.storage.close()
    # Reconstruct the preceding schema from an isolated fixture containing no reports.
    with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
        connection.execute("DROP TRIGGER immutable_validation_update")
        connection.execute("DROP TRIGGER immutable_validation_delete")
        connection.execute("DROP TABLE patch_validations")
        connection.execute("PRAGMA user_version = 4")
    migrated = AnalysisStorage(env.settings)
    try:
        assert migrated.get_patch(proposal.manifest.patch_id) == proposal
        assert migrated.get_source_manifest(sample.analysis.analysis_id) == sample.manifest
        with sqlite3.connect(env.directory / "analyses.sqlite3") as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
            assert connection.execute("SELECT COUNT(*) FROM patch_validations").fetchone()[0] == 0
    finally:
        migrated.close()
