# CascadeRouter: Backend Test Report

**Date:** 2026-10-29 · **Branch:** `backend/benchmark` · **Author:** Aditya (Testing, Metrics & Docs)

**Environment:** Python 3.11.15, FastAPI 0.162.0, Pydantic 2.14.1, OpenAI SDK 3.41.0, macOS. CI runs the same suite on Ubuntu with Python 3.11.

## Summary

| Metric | Result |
| :--- | :--- |
| Backend tests | **428 passed, 1 skipped** (the skip is the opt-in live Nebius test) |
| Line coverage (`backend/`) | **98%** (2,755 statements, 61 missed) |
| CI gate | `pytest --cov=backend --cov-fail-under=95` |
| Sample-repo regression suite (`tests/fixtures/sample_repo`) | 6 passed, both unpatched and patched |
| Network / money used by the suite | **None.** The LLM is a test double inside `tests/`; nothing is billed. |

Reproduce:

```bash
source .venv/bin/activate
pytest -q --ignore=tests/fixtures --cov=backend --cov-report=term-missing
```

## Tests by area

| Area | Tests | What is covered |
| :--- | ---: | :--- |
| `tests/compiler` | 256 | scanner, DAG, cases, sandbox, prompt capture, evaluator, metrics, optimizer, runner, policy, patch, regression |
| `tests/api` | 56 | every endpoint, `types.ts` contract (fields, optionality, literal unions, primitive types), full scan → benchmark → optimize flow, status codes, host/rate/body limits, data-source modes |
| `tests/services` | 35 | Nebius streaming client (usage, TTFT, error mapping), record/replay, optimization service with real sandbox |
| `tests/runtime` | 28 | dispatch, validation-triggered fallback, safe degradation, async, streams, tool calls, policy loading |
| `tests/test_config.py` | 24 | env parsing and validation, `.env` isolation, key redaction |
| `tests/test_guardrails.py` | 15 | token bucket, spend reservations under concurrency, cancellation charging, streamed body limit |
| `tests/test_schemas.py`, `tests/test_store.py` | 13 | schema validation, scan/run stores, eviction |
| `tests/integration` | 2 | end-to-end pipeline on the sample repo; opt-in live Nebius smoke test |

## Coverage by module

| Module | Cover | | Module | Cover |
| :--- | ---: | --- | :--- | ---: |
| `api/deps.py` | 100% | | `compiler/shadow_runner.py` | 100% |
| `api/routes.py` | 98% | | `compiler/router_optimizer.py` | 97% |
| `compiler/ast_scanner.py` | 97% | | `compiler/policy_generator.py` | 100% |
| `compiler/dag_builder.py` | 96% | | `compiler/patch_generator.py` | 96% |
| `compiler/cases.py` | 99% | | `compiler/regression_runner.py` | 98% |
| `compiler/sandbox.py` | 97% | | `runtime/cascade_router.py` | 99% |
| `compiler/prompt_capture.py` | 97% | | `services/nebius_client.py` | 96% |
| `compiler/evaluator.py` | 96% | | `services/recordings.py` | 99% |
| `compiler/metrics.py` | 100% | | `services/optimization.py` | 100% |
| `config.py`, `schemas.py`, `main.py`, `store.py` | 100% | | `guardrails.py` | 97% |

## Adversarial review rounds

Every phase was reviewed by independent reviewers who tried to break the code. A separate verifier then had to reproduce each finding before it counted. Every confirmed finding was fixed and got a regression test.

| Round | Scope | Confirmed defects | Status |
| :--- | :--- | ---: | :--- |
| 1 | P0–P1: config, schemas, metrics, evaluator | 18 | 17 fixed in code; the free-text similarity scoring item was resolved by a plan change |
| 2 | P2: scanner, DAG, `/api/scan` | 16 | all fixed |
| 3 | P3–P6: benchmark, optimize, patch, regression, runtime, guardrails | 21 | all fixed |

Examples of what the reviews caught:
- **Scan crashes:** one deeply nested or FIFO file used to crash or hang the whole scan.
- **Spend cap overshoot:** concurrent calls could go past the cap together, and cancelled calls were never charged.
- **Forged capture results:** target code could forge the capture result and send `max_tokens: 999999` to Nebius.
- **Patch problems:** diffs failed to apply to files with CRLF line endings or a BOM, and `create(...).choices` chains couldn't be patched.
- **Wrong evaluation:** the evaluator graded the first JSON example in a reply instead of the final answer.

## Data honesty checks (team rule: no demo data)

| Check | Test |
| :--- | :--- |
| Recorded mode with no recording gives a `failed` cell, never an invented one | `tests/api/test_benchmark_flow.py::test_recorded_mode_without_recordings_reports_failures` |
| Nodes without cases are not benchmarked | `tests/compiler/test_shadow_runner.py::test_nodes_without_cases_are_failed_not_invented` |
| Vacuous cases (any answer would pass) are never sent | `test_vacuous_cases_are_never_sent` |
| Undefined savings are `None`/null, not a fake 0% | `tests/compiler/test_metrics.py::test_aggregate_totals_undefined_is_none_not_zero` |
| Repeated identical requests replay in recorded order | `tests/services/test_recordings.py::test_repeated_identical_requests_replay_in_order` |

## Not covered by this report

- **Live Nebius calls.** `tests/integration/test_live_nebius.py` runs only with `NEBIUS_LIVE_TEST_KEY` set. The model IDs and prices in `config.py` come from the README and have not yet been checked against the live API.
- **Isolation, not a jail.** The sandbox removes credentials but doesn't jail the OS, so target code keeps network and filesystem access (see "Known limitations" in `backend_plan.md`). A child process that detaches itself into its own session can outlive a timeout.
- **Frontend.** Its build and type checks run in the separate `frontend-check` CI job.
