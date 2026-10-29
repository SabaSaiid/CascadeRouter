# CascadeRouter — Backend Plan

> One-time plan written 2026-10-29 by Aditya (backend). Status is tracked in the checklist at the bottom.

## 1. Where the repo stands

| Area | State |
| :--- | :--- |
| `frontend/` | Done. Three-pane workbench running on `mockData.ts`. `services/api.ts` already calls the backend endpoints below and falls back to mock data on any error. |
| `docs/architecture.md`, `README.md` | Describe a 6-stage pipeline and a `backend/` tree that **does not exist yet**. |
| `backend/`, `tests/`, `tests/fixtures/sample_repo/` | Missing. CI (`tests.yml`) runs `pytest tests/` with `DATA_SOURCE_MODE=mock`, and ignores failures (`|| true`). |
| `start.sh` | Starts `uvicorn backend.main:app` once `backend/main.py` exists. |
| `docs/demo-scenarios.md`, `docs/test-report.md` | Referenced in README, missing. |

**The contract we have to satisfy is `frontend/src/types.ts` + `frontend/src/services/api.ts`.** `architecture.md §4` shows an older, smaller schema. `types.ts` is the superset, so the backend mirrors `types.ts` field for field.

## 2. API contract (taken from `api.ts`)

| Method | Path | Request | Response |
| :--- | :--- | :--- | :--- |
| GET | `/api/health` | — | `{status, version, data_source, nebius_configured}` |
| GET | `/api/models` | — | `ModelTierConfig[]` (catalog + prices) |
| POST | `/api/scan` | `{repository_path}` | `ScanResult` |
| POST | `/api/benchmark` | `{node_ids, repository_path?, data_source?}` | `{run_id}` (202, runs in background) |
| GET | `/api/runs/{run_id}` | — | `BenchmarkRun` (polled for progress) |
| POST | `/api/optimize` | `{run_id, quality_threshold=0.92}` | `OptimizeResult` (includes patch, policy, regression) |
| POST | `/api/regression` | `{run_id}` | regression-only re-run (UI "Run Regression Suite") |

Notes and gotchas:
- `/api/benchmark` only sends `node_ids`, so the backend has to keep the **latest scan** in memory (a `ScanStore`) to turn node ids back into prompts. If the UI ever sends `repository_path`, we key on that instead.
- `api.ts` overwrites `data_source` with `'live'` on every successful response. The backend still reports the real mode, and **Saba needs to stop overwriting it** (one-line frontend change, noted in §8).
- Errors use FastAPI's normal `{"detail": ...}` with real status codes (400 bad path, 404 unknown run, 409 run not complete, 429 rate/spend cap).

## 3. Target layout

```
backend/
  __init__.py
  main.py                 # app factory, CORS, routers, rate-limit middleware
  config.py               # Settings from env/.env + MODEL_CATALOG (single source for prices)
  schemas.py              # Pydantic v2 mirror of frontend/src/types.ts
  api/
    routes.py             # /api/* handlers (thin, no business logic)
    deps.py               # stores, settings injection
  compiler/
    ast_scanner.py        # ast-only discovery of LLM call sites            (Pritam)
    dag_builder.py        # data-flow edges between nodes                    (Pritam)
    metrics.py            # cost, savings, latency stats                     (Aditya)
    evaluator.py          # deterministic schema/quality scoring             (Aditya)
    shadow_runner.py      # bounded-concurrency benchmark across tiers       (Meenal)
    router_optimizer.py   # min cost s.t. quality ≥ τ & hard checks pass     (Meenal)
    policy_generator.py   # .cascaderouter.yaml                               (Meenal)
    patch_generator.py    # unified diff via AST-located spans               (Meenal)
    regression_runner.py  # tempdir sandbox + pytest, 30s, scrubbed env      (Aditya)
  runtime/
    cascade_router.py     # CascadeRouter.load(yaml).dispatch(...) + escalation
  services/
    nebius_client.py      # AsyncOpenAI against Nebius base URL, streaming for TTFT
    recordings.py         # record/replay for "recorded" mode
    tavily_client.py      # optional, stub only
  store.py                # in-memory ScanStore / RunStore (+ JSON snapshot to runs/)
  guardrails.py           # token-bucket rate limit, daily spend cap
tests/
  compiler/               # unit tests per module
  api/                    # TestClient tests per endpoint
  integration/            # scan → benchmark(mock) → optimize → regression end to end
  fixtures/
    sample_repo/          # demo target: agent/workflow.py + tests/ + cascade_cases.yaml
    recordings/           # recorded Nebius responses for "recorded" mode
```

## 4. Module design

### 4.1 `config.py`
- Plain `os.getenv` + `python-dotenv`, so no new dependency. Every key in `.env.example` is read.
- `MODEL_CATALOG: list[ModelSpec]` is built from the `MODEL_TIER_*` / `PRICE_*` env vars and matches `NEMOTRON_CATALOG` in `types.ts`. Efficient and Efficient-Alt share the efficient prices.
- `get_settings()` is cached, and tests override it through FastAPI dependency overrides.

### 4.2 `schemas.py`
- Mirrors `LLMNode`, `ScanResult`, `BenchmarkMetric`, `NodeBenchmarkResult`, `BenchmarkRun`, `OptimizationDecision`, `OptimizeResult`, `ModelTierConfig`, plus request models.
- `GraphEdge` is `tuple[str, str]`, which serialises to a JSON array as the UI expects.
- Optional TS fields (`?`) become `Optional[...] = None`. We never emit fake `0`s, because the UI shows `—` for null.
- A contract test parses `types.ts` interface field names and checks them against the Pydantic `model_fields`, so drift fails CI.

### 4.3 `metrics.py` (Aditya)
- `estimate_cost(model_id, in_tok, out_tok) -> float` uses the catalog prices.
- `cost_savings_pct(baseline, optimized) -> float | None`. Returns `None` when baseline ≤ 0 (same as `utils/metrics.ts`).
- `latency_reduction_pct`, `percentile(values, p)`, `summarize_latencies -> {median, p95, mean}`.
- `aggregate_totals(decisions)` gives total baseline/optimized cost, total reduction %, and **mean** latency reduction across optimized nodes.
- Token counts come from the API `usage` field. If it's missing, we estimate with a chars/4 heuristic and set `is_estimated=True`.

### 4.4 `evaluator.py` (Aditya)
Deterministic, no LLM judge. The score is in [0, 1]:

| Check | Weight | Hard? |
| :--- | :---: | :---: |
| Output parses as JSON (when node has `expected_schema` or `response_format=json_object`) | 0.30 | yes |
| Required fields present | 0.25 | yes |
| Types and enums match schema | 0.20 | no |
| Field agreement with reference output (case's `expected` or the Ultra baseline) | 0.25 | no |

- For free-text nodes (no schema), the checks are non-empty, `must_include` / `must_not_include` phrases from the case file, and a length window. Weights are renormalised. Token-overlap similarity against a reference is deliberately **not** scored, because it unfairly fails correct paraphrases. Free-text quality is set by explicit case assertions.
- Only JSON objects and arrays count as parsed output. Bare scalars, `NaN`/`Infinity`, and pathologically nested input are rejected without crashing.
- `passes_validation = all hard checks pass and score ≥ τ`. Every failed check adds a human-readable string to `validation_errors` (the UI shows these).
- A small built-in JSON-schema subset (type/properties/required/enum/items) so we don't add `jsonschema` as a dependency.
- Tolerates fenced ```json blocks and leading prose (we pull out the first JSON object).

### 4.5 `ast_scanner.py` + `dag_builder.py` (Pritam, interface fixed here)
- Walks `*.py` and skips `venv`, `.git`, `node_modules`, `tests`. Parses with `ast.parse` only and never imports.
- Detects `*.chat.completions.create(...)`, `*.completions.create(...)`, `*.responses.create(...)`.
- Extracts the `model=` literal (or a module constant it points to), `response_format`, `max_tokens`, the enclosing function and its docstring, the prompt constant name (the first `Name` inside `messages`), the snippet (`ast.get_source_segment`), and `expected_schema`. For the schema, priority is a sibling `*_SCHEMA` dict literal, then a Pydantic model in `response_format`.
- `node_id = f"node_{function_name}"`, made unique with a suffix.
- DAG: an edge A→B when B's function is called with A's return value, or when both are called in sequence inside one orchestrator function (`ast` data-flow over assignments). Self-loops are removed and the graph is checked for cycles.
- `detected_framework` comes from imports (`openai`, `langchain`, `litellm`).
- Path safety: `repository_path` must resolve under `ALLOWED_SCAN_ROOTS` (default: repo root). Symlinks are rejected, with a 2 MB per-file cap and a 500-file cap.

### 4.6 Benchmark cases
To benchmark a node we need real inputs. The source of truth is `cascade_cases.yaml` at the target repo root:
```yaml
node_classify_intent:
  - input: "I was double charged on my invoice"
    expected: {category: billing}
```
`vars` are the keyword arguments for the node's function. A `client` argument (or the module-level `client`) is injected automatically.

**Prompt capture (exact prompts, no guessing):** for each case, the backend runs the node's function once in the same sandbox the regression runner uses: a subprocess with a scrubbed env, **no API key**, a timeout, and no network client. A capturing test double stands in for the client. It records the exact `messages` / `response_format` / `max_tokens` of the call and then aborts. The backend then sends those captured messages to each Nemotron tier itself. Untrusted code never sees credentials, and every benchmark uses the prompt the app really builds, f-strings and history included.

If a node has no cases, it gets no benchmark. Its metrics are reported as `failed` with the error "no benchmark cases", and the optimizer keeps the baseline (`inconclusive`). We never invent inputs.

### 4.7 `shadow_runner.py` + `nebius_client.py` (Meenal)
- `asyncio.Semaphore(BENCHMARK_CONCURRENCY)` and a per-call timeout of `BENCHMARK_TIMEOUT_SECONDS`. Each (node × model × case) is one task.
- **live**: `AsyncOpenAI(base_url=NEBIUS_BASE_URL)` with `stream=True` and `stream_options={"include_usage": True}`. TTFT is the first content delta, total latency is wall-clock.
- **recorded**: replays from `tests/fixtures/recordings/*.json` with the same metric shape and `is_estimated=False`.
- **No demo data in the backend.** The backend never makes up outputs, tokens, latencies, or scores. `mock` is a frontend-only mode (`mockData.ts`). If the backend receives `DATA_SOURCE_MODE=mock`, it treats it as `recorded`. If no recording exists for that request, it returns 409 with a clear message instead of making numbers up.
- Live mode writes recordings (`RECORD_RUNS=true`), so a single paid, real run gives a free and honest replay for judges.
- Tests inject a fake LLM client through dependency injection. That's a test double that lives only in `tests/` and never ships.
- Progress: `progress_pct = done/total*100`, and `current_step` is something like `"Super-VL × node_extract_entities (7/12)"`.
- Per-node `recommended_model_id` is filled in when its models finish (it reuses the optimizer's selection function).
- Failures (timeout, 4xx/5xx) set `status='failed'`, `passes_validation=False`, and the error text goes into `validation_errors`. They never crash the run.

### 4.8 `router_optimizer.py` (Meenal)
- Candidates are metrics where `passes_validation` is true and `quality_score ≥ τ`.
- Choose the lowest `estimated_cost_usd`. If two are within 2% on cost, take the lower median latency (the same rule as `verdictSentence` in the UI).
- `baseline_model = node.current_model`. If that wasn't benchmarked, fall back to the Powerful tier.
- `fallback_model` is the cheapest passing model strictly above the chosen tier, otherwise Ultra.
- Status values:
  - `optimized`: the chosen model is cheaper than the baseline.
  - `baseline_retained`: nothing cheaper passes.
  - `inconclusive`: the baseline failed or too many calls failed (more than 50%).

### 4.9 `policy_generator.py` / `patch_generator.py` (Meenal)
- The policy is YAML via `yaml.safe_dump`. One per-node snippet (`policy_yaml`), plus the combined file that matches the `combined_policy_yaml` shape in mockData.
- The patch replaces the AST span of each `client.chat.completions.create(` call. The call becomes `cascade_router.dispatch(node_id=..., client=client, fallback_tier=..., ...)` with the `model=` kwarg removed. It also inserts the import and the `CascadeRouter.load(...)` line once.
- The diff is built with `difflib.unified_diff`, and the patched file has to pass `ast.parse` before we emit anything.

### 4.10 `runtime/cascade_router.py`
- `CascadeRouter.load(path)` and `dispatch(node_id, client, fallback_tier=None, validator=None, **kwargs)`.
- `dispatch` calls the primary model, then validates (JSON schema from the policy, if `enforce_schema`). On failure or exception it escalates to the fallback, up to `max_retries`. There are no dependencies beyond PyYAML.
- It's shipped into the sandbox as an importable `cascaderouter` module, so the patched sample repo imports cleanly.

### 4.11 `regression_runner.py` (Aditya)
- Copies the target repo into `tempfile.mkdtemp(prefix="temp_patch_")`, drops in the `cascaderouter` runtime + `.cascaderouter.yaml`, applies the patched file contents, and runs `python -m pytest -q` with `timeout=REGRESSION_TIMEOUT_SECONDS`.
- The env is scrubbed: only `PATH`, `PYTHONPATH`, `HOME=tmp`, and `CASCADE_OFFLINE=1`. No `NEBIUS_API_KEY` and nothing else from the host.
- The sample repo's tests use a fake client (no network), so regression is deterministic.
- We parse per-test outcomes from `-rA` output and map them to each node's `regression_log`. A timeout means `passed=False` with the log saying so. The tempdir is always cleaned up.

### 4.12 Guardrails
- A token-bucket rate limit keyed by client IP (`RATE_LIMIT_PER_MINUTE`). It's enabled when `ENABLE_RATE_LIMITING`, and `/api/health` is exempt.
- The daily spend cap is a running sum of live `estimated_cost_usd` that resets at UTC midnight. Live benchmarks are refused with 429 once the projected spend would go over the cap. Mock and recorded runs are never capped.
- The API key is never logged or returned. `/api/health` only exposes the `nebius_configured: bool`.

## 5. Phases

| # | Phase | Output | Owner |
| :-: | :--- | :--- | :--- |
| P0 | Scaffold | `backend/` package, config, schemas, `main.py` with health/models, CORS, test harness, contract test vs `types.ts` | Aditya |
| P1 | Metrics + evaluator | `metrics.py`, `evaluator.py` + unit tests | Aditya |
| P2 | Sample repo + scanner | `tests/fixtures/sample_repo`, `ast_scanner.py`, `dag_builder.py`, `/api/scan` | Pritam (Aditya unblocks with fixture) |
| P3 | Benchmark | `nebius_client.py`, `shadow_runner.py`, stores, `/api/benchmark`, `/api/runs/{id}`, mock + recorded modes | Meenal |
| P4 | Optimize | `router_optimizer.py`, `policy_generator.py`, `patch_generator.py`, `/api/optimize` | Meenal |
| P5 | Runtime + regression | `runtime/cascade_router.py`, `regression_runner.py`, `/api/regression` | Meenal / Aditya |
| P6 | Hardening | guardrails, live recording, integration suite, CI without `|| true`, `docs/test-report.md`, `docs/demo-scenarios.md` | Aditya |

Definition of done for every phase: `pytest tests/ -q` is green with no network (tests inject fake clients), and the frontend works against the real backend.

## 6. Testing strategy
- Unit tests for each compiler module, using pure functions with no I/O.
- API tests with `fastapi.testclient.TestClient` for status codes and response shapes.
- A contract test: `types.ts` interfaces must match the Pydantic fields.
- Integration: scan the sample repo, benchmark with an injected fake client, optimize, and check that regression passed, savings are above 0, and the patch parses.
- Live smoke test (`-m live`, skipped unless `NEBIUS_API_KEY` is set): one node on Nano.

## 7. Risks
| Risk | Mitigation |
| :--- | :--- |
| Nebius model ids or prices change | Everything comes from env and the catalog. Recordings are the demo default. |
| Live latency or rate limits during judging | Default the hosted demo to `recorded`, with the spend cap and rate limit. |
| Scanner misses calls in unfamiliar repos | The demo targets the bundled sample repo. Unknown patterns are logged, not fatal. |
| Patch breaks code | `ast.parse` gate + sandbox regression before `regression_passed=True`. |
| Untrusted path scanning on hosted demo | Allow-listed roots, no symlinks, file caps. |

## 8. Cross-team asks
- **Saba (frontend)**: in `api.ts`, keep the backend's `data_source` instead of forcing `'live'`. Wire up the "Run Regression Suite" button to `/api/regression`. Poll `/api/runs/{id}` until `status === 'complete'`.
- **Pritam**: keep the `LLMNode` field names from §4.5. The sample repo fixture in P2 is a starting point you can take over.
- **Meenal**: the interfaces in §4.7–4.10 are proposals, so change them freely, but keep `schemas.py` in sync with `types.ts`.

## 9. Status
Working rules: small commits per step, no demo data in `backend/`, every module unit-tested, and `pytest` green before each commit.

- [x] P0 Scaffold
- [x] P1 Metrics + evaluator
- [x] P2 Sample repo + scanner (`/api/scan`)
- [ ] P3 Benchmark
- [ ] P4 Optimize
- [ ] P5 Runtime + regression
- [ ] P6 Hardening
