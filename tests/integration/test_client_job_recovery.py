"""Durable recovery and conflicting requests verified through the actual client."""
import json
import pytest

from acceptance_support import client_case, serve, tree_bytes


@pytest.mark.parametrize("initial", ["queued", "running", "cancelling"])
def test_client_observes_honest_restart_recovery(job_environment, initial):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    if initial != "queued":
        env.storage.transition_job(job.run_id, ("queued",), status="running")
    if initial == "cancelling":
        env.storage.transition_job(job.run_id, ("running",), status="cancelling", cancellation_reason="requested")
    before = tree_bytes(env.repository)
    with serve(env.settings, benchmark_registry=env.registry, benchmark_executor=env.executor, allow_test_benchmarks=True) as server:
        value = client_case(server.base, "read-job.mjs", {"run_id": job.run_id, "expected": "complete" if initial == "queued" else "interrupted"})
        assert server.app.state.scan_service.storage.get_job(job.run_id).model_dump(mode="json") == value
    assert len(env.executor.calls) == (1 if initial == "queued" else 0)
    assert env.storage.get_job(job.run_id).model_dump(mode="json") == value
    assert tree_bytes(env.repository) == before


def test_client_concurrent_cancellation_preserves_terminal_records_and_never_starts_queued_job(job_environment):
    env = job_environment
    env.executor.release.clear()
    before = tree_bytes(env.repository)
    with serve(env.settings, benchmark_registry=env.registry, benchmark_executor=env.executor, allow_test_benchmarks=True) as server:
        values = client_case(server.base, "cancellation.mjs", {"request": env.request.model_dump(mode="json")})
        for value in values:
            assert server.app.state.scan_service.storage.get_job(value["run_id"]).model_dump(mode="json") == value
    assert len(env.executor.calls) == 1
    assert all(env.storage.get_job(value["run_id"]).status == "cancelled" for value in values)
    assert tree_bytes(env.repository) == before


def test_corrupt_job_payload_cannot_become_client_success_after_restart(job_environment):
    env = job_environment
    plan = env.registry.resolve(env.request, env.analysis, env.settings, env.executor)
    job = env.storage.create_job(env.request, plan, lambda _: None)
    # A terminal cancelled fixture avoids recovery execution. Only this temporary DB is corrupted.
    job = env.storage.transition_job(job.run_id, ("queued",), status="cancelled", cancellation_reason="requested")
    payload = job.model_dump(mode="json")
    payload["run_id"] = "run_" + "f" * 32
    # Simulate operator-owned disk corruption, restoring the exact trigger before
    # serving requests. Runtime integrity/authorization checks are never bypassed.
    with env.storage._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='immutable_job_terminal'").fetchone()[0]
        connection.execute("DROP TRIGGER immutable_job_terminal")
        try:
            connection.execute("UPDATE jobs SET payload=? WHERE run_id=?", (json.dumps(payload).encode(), job.run_id))
        finally:
            connection.execute(ddl)
        connection.commit()
    before = tree_bytes(env.repository)
    with serve(env.settings) as server:
        assert client_case(server.base, "read-job.mjs", {"run_id": job.run_id, "corrupt": True}) == {"rejected": True}
    assert tree_bytes(env.repository) == before
