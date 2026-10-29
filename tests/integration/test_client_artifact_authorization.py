"""Existing synthetic artifacts never grant production or cross-repository access."""
from backend.config import BackendConfig
from acceptance_support import client_case, serve, tree_bytes


def test_client_cannot_turn_retained_test_proposals_or_reports_into_production_authority(validation_environment, tmp_path):
    env = validation_environment
    sample = env.build_patch()
    report = env.storage.save_validation(env.validation_report(sample))
    proposal = env.storage.get_patch(report.result.patch_id)
    record = sample.record
    plan = sample.sample.job.plan
    assert proposal.manifest.provenance == report.result.provenance == plan.provenance == "test"
    assert proposal.manifest.patch_format == "literal-spans.v1"
    assert report.result.status == "validated" and all(file.syntax == "passed" for file in report.result.files)
    before = tree_bytes(env.repository)
    payload = dict(repository=str(env.repository), analysis_id=sample.analysis.analysis_id,
                   run_id=sample.sample.job.run_id, optimization_id=record.optimization_id,
                   patch_id=proposal.manifest.patch_id, validation_id=report.validation_id,
                   case_set=plan.case_set.model_dump(), evaluation_profile=plan.evaluation_profile.model_dump())
    # No approval stubs: actual endpoints must deny these test-only compiler artifacts.
    with serve(env.settings) as server:
        assert client_case(server.base, "artifact-access.mjs", {**payload, "kind": "unavailable", "status": 503}) == {"denied": 4}
    other = tmp_path / "new-policy-root"
    other.mkdir()
    changed = BackendConfig(permitted_repository_roots=[other], storage_directory=env.directory)
    with serve(changed) as server:
        assert client_case(server.base, "artifact-access.mjs", {**payload, "kind": "authorization", "status": 403}) == {"denied": 9}
    assert env.storage.get_patch(proposal.manifest.patch_id) == proposal
    assert env.storage.get_validation(report.validation_id) == report
    with env.storage._connection() as connection:
        assert connection.execute("SELECT count(*) FROM patch_validations").fetchone()[0] == 1
    assert tree_bytes(env.repository) == before
