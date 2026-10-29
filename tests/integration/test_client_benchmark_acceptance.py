"""Real client -> API -> offline test executor -> immutable results -> optimizer gate."""
from contextlib import closing

import pytest

from acceptance_support import client_case, serve, tree_bytes
from backend.services.storage import AnalysisStorage


@pytest.mark.parametrize("evaluation", ["passed", "failed"])
def test_test_benchmark_evaluation_and_optimization_remain_honest_after_reload(offline_environment, evaluation):
    env = offline_environment
    if evaluation == "failed":
        outputs = {(model.identifier, case.identifier): case.expected_output
                   for model in env.registry.document.models for case in env.registry.document.case_sets[0].cases}
        outputs["local/candidate", "case-one"] = "SYNTHETIC_TEST_MISMATCH"
        registry, _, executor = env.make_offline(outputs=outputs)
    else:
        registry, executor = env.registry, env.executor
    request = {**env.request.model_dump(mode="json"), "idempotency_key": "acceptance-test-plan"}
    before = tree_bytes(env.repository)
    with serve(env.settings, benchmark_registry=registry, benchmark_executor=executor, allow_test_benchmarks=True) as server:
        value = client_case(server.base, "benchmark.mjs", {"request": request, "evaluation": evaluation})
        storage = server.app.state.scan_service.storage
        job = storage.get_job(value["job"]["run_id"])
        assert job.model_dump(mode="json") == value["job"]
        assert storage.get_optimization(value["optimization"]["optimization_id"]).response.model_dump(mode="json") == value["optimization"]
        assert job.result.metrics.failed == (1 if evaluation == "failed" else 0)
        encoded = job.model_dump_json()
        assert "PRIVATE_CAPTURE" not in encoded and "PRIVATE_LOCAL_INPUT" not in encoded
    with closing(AnalysisStorage(env.settings)) as storage:
        assert storage.get_job(job.run_id) == job
        with storage._connection() as connection:
            assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    assert tree_bytes(env.repository) == before
