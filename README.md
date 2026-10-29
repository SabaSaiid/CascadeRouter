# CascadeRouter

**A FinOps and latency compiler for LLM calls in Python agent codebases.** It finds every LLM call site in a repository, benchmarks each one against NVIDIA Nemotron tiers on Nebius Token Factory, picks the cheapest model that still passes your quality checks, and emits a routing policy, a reviewable patch, and a regression result.

[![Hackathon](https://img.shields.io/badge/Nebius%20%C3%97%20NVIDIA-Global%20AI%20Hackathon%202026-76B900?logo=nvidia&logoColor=white)](https://devpost.com)
[![Track](https://img.shields.io/badge/Track-1%3A%20Coding%20%26%20Agentic%20Engineering-blue)](https://devpost.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![TypeScript 6](https://img.shields.io/badge/TypeScript-6.0-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/tests-428%20passed%2C%201%20skipped-brightgreen)](docs/test-report.md)
[![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen)](docs/test-report.md)

---

## What it does

**Problem.** Agent codebases often hard-wire one large frontier model into every call, including simple ones such as classification, field extraction or fixed-format JSON. Each of those calls pays frontier-model prices and latency for work a smaller model may handle just as well.

**Approach.** CascadeRouter treats this as a compile step:

1. **Scan.** Static analysis with Python's `ast` finds OpenAI-SDK-style LLM call sites and builds a dependency DAG between them. Scanning never imports the target code.
2. **Benchmark.** It captures each call's real request in a sandbox and replays it against all four Nemotron models. Each answer is scored by a deterministic evaluator (no LLM judge) against hand-written cases in `cascade_cases.yaml`.
3. **Optimize.** For each call site it picks the cheapest model that passes the hard checks and meets the quality threshold (default `0.92`), and chooses a fallback model.
4. **Emit.** It writes a `.cascaderouter.yaml` routing policy and a unified diff that routes the call through a small runtime wrapper. It then runs the target repo's own pytest suite against the patched copy.

The runtime wrapper (`cascaderouter.py`) reads the policy in production. It calls the chosen model and, when the response fails a structural check, retries once on the fallback model.

---

## How it works

The pipeline is three HTTP calls. The benchmark runs in the background and the client polls for it.

```
POST /api/scan ─────────► ast_scanner ──► dag_builder ──► ScanStore (in memory)
                          (parse only;     (data-flow +
                           never imports)   sequence edges)

POST /api/benchmark ────► spend-cap / projected-cost check ──► 202 {run_id}
  └ background task:      load cascade_cases.yaml
                          prompt_capture   (runs node function in sandbox with a fake client)
                          mark vacuous cases failed
                          node × case × model completions   (Semaphore(BENCHMARK_CONCURRENCY))
                          evaluator ──► aggregate_metric ──► select_model
GET  /api/runs/{run_id} ─► progress + per-model metrics

POST /api/optimize ─────► decide_node (per node)
                          aggregate_totals
                          build_policy ──► .cascaderouter.yaml
                          build_patches  (optimized nodes only)
                          run_regression (only if a file was patched; pytest in sandbox)
                          ──► OptimizeResult (cached per run_id + threshold)
```

### Stage details

| Stage | Module | Behaviour |
| :--- | :--- | :--- |
| Scan | `backend/compiler/ast_scanner.py` | A call counts as an LLM call when its attribute chain ends in `chat.completions.create`, `completions.create` or `responses.create`, and some module imports `openai`, `langchain_openai`, `litellm`, `together` or `groq`. The model argument resolves from a string literal, a single local literal assignment, or a module-level constant; anything else becomes `<dynamic>` or `<unspecified>`. Skips `tests/`, `test/`, `build/`, `dist/`, venvs (`venv`, `.venv`, `env`), `site-packages`, `node_modules`, dot-dirs, symlinked dirs, `test_*.py` and `*_test.py`. Limits: 2 MB per file, 500 files, 20 MB total. Node ids are `node_<function_name>` (module-level calls: `node_<file>_l<line>`; duplicates get a `__2` suffix). |
| DAG | `backend/compiler/dag_builder.py` | Edges come from data flow (one node's output passed to another) and from call sequence. Branches are handled, and any edge that would close a cycle is dropped. |
| Cases | `backend/compiler/cases.py` | Reads `cascade_cases.yaml` at the scanned repo's root: `node_id -> [ {vars, expected, must_include, must_not_include, min_chars, max_chars} ]`, at most 20 cases per node. **A node with no cases is not benchmarked.** |
| Capture | `backend/compiler/prompt_capture.py` | Imports the node's module in a sandbox copy, patches the OpenAI client with a fake, calls the function with each case's `vars`, and records the request at the call site. It makes no network calls and uses no credentials. Only `chat.completions` calls inside functions can be benchmarked. `max_tokens` is capped at 2048. |
| Benchmark | `backend/compiler/shadow_runner.py` | Runs every node × case × model. Per cell: mean tokens, median latency and TTFT, mean cost. Quality = the sum of case scores divided by all cases, with failed calls scored 0. |
| Evaluate | `backend/compiler/evaluator.py` | Deterministic. Structured output is scored on parse (hard), required fields (hard), types/enums, and agreement with the reference. Free text is scored on non-empty (hard), `must_include` (hard), `must_not_include` (hard), and a length window. `<think>` blocks are stripped. Supports a JSON Schema subset: `type`, `properties`, `required`, `enum`, `items`. |
| Select | `backend/compiler/router_optimizer.py` | Candidates must pass the hard checks and have quality >= threshold. The cheapest wins; when several are within 2% of the cheapest cost, the lowest latency wins. Status is `optimized`, `baseline_retained` or `inconclusive`. The fallback is the cheapest passing higher-tier model, or else Nemotron-3 Ultra. |
| Policy | `backend/compiler/policy_generator.py` | `.cascaderouter.yaml` (version `1.0`). For each node it records primary, fallback and baseline model, routing conditions (`enforce_json`, `required_fields`, `max_retries: 1`) and the evidence. |
| Patch | `backend/compiler/patch_generator.py` | Rewrites `client.chat.completions.create(...)` to `cascade_router.dispatch(node_id=..., client=client, ...)`, or to `dispatch_async` inside `async def`, and adds the import and loader lines. It refuses calls that use `stream`, `tools`, `functions`, `tool_choice` or `function_call`. Output is a unified diff. |
| Regression | `backend/compiler/regression_runner.py`, `sandbox.py` | Copies the scanned repo to a temp dir and writes in the patched files, the policy, and the runtime as `cascaderouter.py`. Runs `python -m pytest -q` with `REGRESSION_TIMEOUT_SECONDS`. If no tests are collected, the patch is reported as **unverified**, not passed. |

### Model catalog (defaults)

| Tier | Model id | Input $/1M | Output $/1M |
| :--- | :--- | ---: | ---: |
| efficient | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 0.06 | 0.24 |
| efficient (alt) | `nvidia/Nemotron-3_5-Lightning` | 0.06 | 0.24 |
| balanced | `nvidia/Nemotron-3.5-Super-VL` | 0.30 | 0.90 |
| powerful | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1.00 | 3.00 |

Model ids and prices are configurable defaults in `backend/config.py`. Override them with the `MODEL_TIER_*` and `PRICE_*` env vars. They have not been checked against the live Nebius pricing API (see [docs/test-report.md](docs/test-report.md)). Cost per call is `in_tokens/1e6 * price_in + out_tokens/1e6 * price_out`. When the provider reports no usage, tokens are estimated as `ceil(chars/4)` and the cell is flagged `is_estimated`.

---

## Quickstart

### Prerequisites

- Python 3.11 (CI and development use 3.11)
- Node.js `^20.19.0` or `>=22.12.0` (required by Vite 8) and npm
- A Nebius Token Factory API key, needed only for live benchmarking

### Backend

```bash
git clone https://github.com/SabaSaiid/CascadeRouter.git
cd CascadeRouter

python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then set NEBIUS_API_KEY in .env
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Check it is up:

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","version":"0.1.0","environment":"development","data_source":"live","nebius_configured":true}
```

Interactive OpenAPI docs are served at `http://127.0.0.1:8000/docs`.

### Frontend

```bash
cd frontend
npm install
VITE_DATA_SOURCE=live npm run dev  # Vite on http://localhost:5173
```

The UI defaults to **mock** mode, which shows the bundled fixtures in `frontend/src/services/mockData.ts` and never calls the backend. To use the backend, either set `VITE_DATA_SOURCE=live` as above or click the data-source badge in the header to switch modes. The backend URL comes from `VITE_API_BASE_URL` (default `http://localhost:8000`).

### Both at once

```bash
./start.sh
```

`start.sh` does the following:

- Copies `.env.example` to `.env` if `.env` is missing.
- Activates `./venv` or `./.venv`.
- Starts `uvicorn backend.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload`.
- Runs `npm install` in `frontend/` if `node_modules` is missing, then starts `npm run dev` on port 5173.
- Stops both processes when it exits.

It does **not** install Python dependencies. Run `pip install -r requirements.txt` first. `HOST` and `PORT` are read from the shell only; values in `.env` do not affect them.

### End-to-end with curl

This walkthrough uses the bundled sample repo (`tests/fixtures/sample_repo`, a customer-support triage agent with three Ultra-550b calls and six labelled cases):

```bash
# 1. Scan: returns 3 nodes and 3 edges
curl -s -X POST localhost:8000/api/scan -H 'Content-Type: application/json' \
  -d '{"repository_path":"tests/fixtures/sample_repo"}'

# 2. Benchmark: returns 202 {"run_id":"run_..."}
curl -s -X POST localhost:8000/api/benchmark -H 'Content-Type: application/json' \
  -d '{"node_ids":["node_classify_customer_intent","node_extract_ticket_metadata","node_generate_support_resolution"]}'

# 3. Poll until status is "complete"
curl -s localhost:8000/api/runs/<run_id>

# 4. Optimize: decisions, policy YAML, patch diff, regression result
curl -s -X POST localhost:8000/api/optimize -H 'Content-Type: application/json' \
  -d '{"run_id":"<run_id>","quality_threshold":0.92}'
```

To scan your own project, add its path to `ALLOWED_SCAN_ROOTS` and put a `cascade_cases.yaml` at its root. Example:

```yaml
# excerpt from tests/fixtures/sample_repo/cascade_cases.yaml
node_classify_customer_intent:
  - vars: {query: "I was charged twice for my subscription this month, please refund one charge."}
    expected: {category: billing}
node_generate_support_resolution:
  - vars:
      ticket: "The desktop app crashes with error 0x80070005 every time I open a project."
      intent: {category: tech_support}
      metadata: {account_id: "", os_version: "", error_code: "0x80070005"}
    must_include: ["1.", "2."]
    min_chars: 80
    max_chars: 4000
```

A case with no assertions (no `expected`, no include/exclude list, no length bound) and no schema on the node counts as vacuous. It is never sent to a model, but it counts as a failed case for every model (score 0, hard check fails), so a node with any vacuous case cannot be optimized and stays `baseline_retained`.

---

## Configuration

Settings load from the repo-root `.env`; real environment variables override it. An invalid value fails at startup with `ConfigError`. Booleans accept `1/true/yes/on` and `0/false/no/off`.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `NEBIUS_API_KEY` | *(empty)* | Required for `live` mode. A value starting with `your-` counts as unset. |
| `NEBIUS_BASE_URL` | `https://api.studio.nebius.ai/v1` | OpenAI-compatible endpoint |
| `MODEL_TIER_EFFICIENT` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Model ids, which must be unique |
| `MODEL_TIER_EFFICIENT_ALT` | `nvidia/Nemotron-3_5-Lightning` | Shares the `PRICE_EFFICIENT_*` prices |
| `MODEL_TIER_BALANCED` | `nvidia/Nemotron-3.5-Super-VL` | |
| `MODEL_TIER_POWERFUL` | `nvidia/Nemotron-3-Ultra-550b-a55b` | |
| `PRICE_{EFFICIENT,BALANCED,POWERFUL}_{INPUT,OUTPUT}` | see catalog | USD per 1M tokens, >= 0 |
| `QUALITY_THRESHOLD` | `0.92` | Threshold used during benchmark runs, in [0, 1]. `/api/optimize` takes its own `quality_threshold` (body default `0.92`). |
| `BENCHMARK_CONCURRENCY` | `4` | Maximum concurrent model calls per run |
| `BENCHMARK_TIMEOUT_SECONDS` | `45` | Per-call timeout for the Nebius client |
| `REGRESSION_TIMEOUT_SECONDS` | `30` | Timeout for prompt capture and for the regression sandbox |
| `DATA_SOURCE_MODE` | `live` | `live`, `recorded` or `mock`. The backend treats `mock` as `recorded`. |
| `RECORD_RUNS` | `false` | Save every successful live response for later replay |
| `RECORDINGS_DIR` | `recordings` | Directory for recordings, resolved against the repo root |
| `ALLOWED_SCAN_ROOTS` | repo root (`.env.example`: `.`) | Comma-separated directories that scans may read |
| `ENABLE_RATE_LIMITING` | `true` | Per-IP token bucket |
| `RATE_LIMIT_PER_MINUTE` | `60` | Bucket capacity |
| `DAILY_SPEND_CAP_USD` | `10.0` | In-memory live-mode cap that resets at UTC midnight |
| `MAX_CONCURRENT_RUNS` | `2` | Benchmark runs allowed at once |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Trusted `Host` headers; `*` disables the check |
| `ENVIRONMENT` | `development` | Reported by `/api/health` |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Used only as shell variables by `start.sh` |
| `TAVILY_API_KEY` | *(empty)* | Parsed but currently unused |

Frontend (Vite, set in the shell or in `frontend/.env`):

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL |
| `VITE_DATA_SOURCE` | `mock` | Mode the UI starts in: `live`, `recorded` or `mock` |

Runtime wrapper:

| Variable | Purpose |
| :--- | :--- |
| `CASCADEROUTER_POLICY` | Explicit path to the policy file. If the file is missing, every call passes through. |
| `CASCADEROUTER_DISABLE` | When set to a non-empty value at the time `CascadeRouter.load()` runs, the router loads no policy and every call passes through unchanged |

---

## API reference

All routes are under `/api`. Every request schema rejects unknown fields. `backend/schemas.py` mirrors `frontend/src/types.ts`, and a contract test keeps the two in sync.

| Method | Path | Body | Returns | Errors |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/api/health` | | `{status, version, environment, data_source, nebius_configured}` | Exempt from rate limiting |
| GET | `/api/models` | | `ModelTierConfig[]` `{id, name, tier, inputPricePerM, outputPricePerM, description, badgeColor}` | |
| POST | `/api/scan` | `{repository_path}` | `ScanResult {repository_path, nodes, graph_edges, timestamp, data_source, scanned_files_count, detected_framework}` | 400 if the path is outside `ALLOWED_SCAN_ROOTS` |
| POST | `/api/benchmark` | `{node_ids: [..], repository_path?}` | **202** `{run_id}` | 400 bad path, or unknown nodes when `repository_path` is given; 409 no stored scan contains all the node ids (run `/api/scan` first); 429 too many runs, spend cap reached, or projected cost over the remaining budget; 503 live mode without `NEBIUS_API_KEY` |
| GET | `/api/runs/{run_id}` | | `BenchmarkRun {run_id, status, progress_pct, current_step, nodes, data_source, created_at}` | 404 unknown run |
| POST | `/api/optimize` | `{run_id, quality_threshold=0.92}` | `OptimizeResult {decisions, total_baseline_cost_usd, total_optimized_cost_usd, total_cost_reduction_pct, avg_latency_reduction_pct, combined_policy_yaml, combined_patch_diff, all_regressions_passed, data_source}` | 404 unknown run; 409 run not complete |

There is no streaming or WebSocket endpoint and no separate regression endpoint: the regression runs inside `/api/optimize`. All state (32 scans, 64 runs) is held in memory in a single process and is lost on restart.

---

## Using the runtime router in your code

The runtime is a single file that needs only the standard library and PyYAML. Vendor it next to your code under the name the patch imports:

```bash
cp backend/runtime/cascade_router.py /path/to/your/project/cascaderouter.py
```

Then put the generated `.cascaderouter.yaml` anywhere at or above the calling module:

```python
from openai import OpenAI
from cascaderouter import CascadeRouter

cascade_router = CascadeRouter.load(__file__)   # walks up from this file to find .cascaderouter.yaml
client = OpenAI(base_url="https://api.studio.nebius.ai/v1", api_key="...")

resp = cascade_router.dispatch(
    node_id="node_classify_customer_intent",
    client=client,
    model="nvidia/Nemotron-3-Ultra-550b-a55b",   # used only if the node is not in the policy
    messages=[{"role": "user", "content": "I was charged twice this month"}],
    validator=lambda r: True,                     # optional extra check
)

print(cascade_router.stats)   # DispatchStats(primary_ok, escalations, passthrough, events)

# Async: await cascade_router.dispatch_async(node_id=..., client=AsyncOpenAI(...), ...)
```

Behaviour:

- **Unknown node, or no policy found:** the call passes through unchanged with your `model`. A missing or invalid policy is logged and never raises.
- **Known node:** the router calls `primary_model`. It escalates to `fallback_model` (up to `max_retries`, which is 1) when the call raises, the text is empty, the node requires JSON and no JSON object parses, required fields are missing, or `validator` returns `False`. If every attempt fails, it returns the first invalid response, or re-raises the last exception if there was none.
- **`stream=True`:** the call goes to the primary model with no validation or fallback.
- The runtime does **not** check `min_quality_score`; only the structural checks and your validator trigger escalation.

---

## Data modes

| Mode | Backend | Frontend |
| :--- | :--- | :--- |
| `live` | Real Nebius calls through the spend-capped client. If `RECORD_RUNS=true`, each successful response is also saved. | Calls the backend |
| `recorded` | Replays saved responses from `RECORDINGS_DIR`, keyed by SHA-256 of `{model, messages, params}`. **It never fabricates data:** a missing recording becomes a per-cell error. | Calls the backend (same as `live`; the UI does not send its mode to the server) |
| `mock` | Treated as `recorded` | Returns the fixtures in `mockData.ts` without calling the backend |

The repo ships **no** `recordings/` directory. Recorded mode only works after at least one live run with `RECORD_RUNS=true`. Until then, every metric fails with `no recording for this request; run once in live mode with RECORD_RUNS=true`.

Scanning is always real static analysis, so `/api/scan` always reports `data_source: "live"`.

---

## Testing

```bash
source .venv/bin/activate
pytest -q                                  # 428 passed, 1 skipped (~21 s)
pytest -q --cov=backend --cov-report=term-missing   # 98% line coverage of backend/
```

The suite runs offline: the LLM is replaced by a test double and nothing is billed. An autouse fixture clears the backend's configuration env vars (`NEBIUS_*`, `MODEL_TIER_*`, `PRICE_*`, ...) and ignores your `.env`. It does not clear the runtime wrapper's `CASCADEROUTER_POLICY` / `CASCADEROUTER_DISABLE`. Tests per area:

| Area | Tests |
| :--- | ---: |
| `tests/compiler` | 256 |
| `tests/api` | 56 |
| `tests/services` | 35 |
| `tests/runtime` | 28 |
| `tests/test_config.py` | 24 |
| `tests/test_guardrails.py` | 15 |
| `tests/test_schemas.py` | 8 |
| `tests/test_store.py` | 5 |
| `tests/integration` | 2 |
| **Total collected** | **429** |

`tests/integration/test_pipeline.py` runs the full scan → DAG → benchmark → optimize → regression pipeline on the sample repo. It then loads the emitted policy into `CascadeRouter`.

The one skipped test is a live smoke test. It is gated on a dedicated key, deliberately **not** `NEBIUS_API_KEY`:

```bash
NEBIUS_LIVE_TEST_KEY=sk-... pytest -m live tests/integration/test_live_nebius.py
```

The sample repo's own suite (the one the regression runner executes) also runs on its own:

```bash
cd tests/fixtures/sample_repo && python -m pytest -q -p no:cacheprovider   # 6 passed
```

**CI** (`.github/workflows/tests.yml`) runs on pushes and PRs to `main`:

- **Backend:** Python 3.11, `pytest tests/ --cov=backend --cov-fail-under=95`.
- **Frontend:** Node 20, `npm ci` and then `npm run build || true`, so a frontend build failure does not fail CI.

CI has no lint step. The frontend has no test script; `npm run lint` (oxlint) is available locally.

---

## Project layout

```
CascadeRouter/
├── backend/
│   ├── main.py                 # FastAPI app factory (backend.main:app)
│   ├── config.py               # Settings, model catalog, prices
│   ├── schemas.py              # Pydantic models (mirror frontend/src/types.ts)
│   ├── guardrails.py           # Rate limit, body-size cap, spend tracker
│   ├── store.py                # In-memory scan and run stores
│   ├── api/                    # routes.py, deps.py (client wiring per data mode)
│   ├── compiler/               # ast_scanner, dag_builder, cases, prompt_capture,
│   │                           # shadow_runner, evaluator, metrics, router_optimizer,
│   │                           # policy_generator, patch_generator, sandbox, regression_runner
│   ├── services/               # llm.py, nebius_client.py, recordings.py, optimization.py
│   └── runtime/cascade_router.py   # Standalone runtime; vendor as cascaderouter.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx, main.tsx, types.ts, App.css, index.css
│   │   ├── components/{repository,benchmark,optimization,layout}/
│   │   ├── services/{api.ts,mockData.ts}
│   │   └── utils/metrics.ts
│   ├── package.json, vite.config.ts, tsconfig*.json, index.html
├── tests/
│   ├── api/ compiler/ services/ runtime/ integration/
│   ├── test_config.py test_guardrails.py test_schemas.py test_store.py
│   ├── conftest.py
│   └── fixtures/sample_repo/   # agent/workflow.py, cascade_cases.yaml, tests/
├── docs/                       # architecture.md, demo-scenarios.md, test-report.md
├── .github/workflows/tests.yml
├── backend_plan.md
├── start.sh
├── requirements.txt
├── pytest.ini
├── .env.example
└── LICENSE
```

---

## Workbench UI

The React app (`frontend/`, page title "CascadeRouter IDE") has three panes:

- **Repository:** call sites with their file and line, the current or recommended model, and a code snippet. Below them is a linear dependency chain built from the DAG edges. The repo picker only offers the bundled sample repo.
- **Benchmark:** a grid of call sites × the four Nemotron models with pass/fail, cost, latency and quality. Clicking a cell opens tokens, TTFT and validation errors.
- **Recommendation:** baseline vs optimized cost per call site, plus Diff, Policy and Tests tabs.

A single header button moves through **Scan repository → Run benchmark → Generate patch**.

Current UI limitations:

- On page load the UI auto-loads a demo run id, which falls back to mock data when the backend is live.
- A benchmark is polled only once rather than in a loop.
- A failed backend call silently falls back to the mock fixtures while the badge still shows the selected mode.
- The Tests tab shows a fixed sample pytest log instead of the backend's regression log.
- The latency summary is not shown.
- The quality threshold is fixed at 0.92.
- The header spend meter compares against a hard-coded $10 and does not read the backend's spend tracker.

The API responses above are the source of truth.

---

## Safety guardrails

These guardrails are implemented in the code:

- **Static scanning.** `/api/scan` only parses files with `ast`; it never imports them. Paths must resolve inside `ALLOWED_SCAN_ROOTS`; anything else, such as `/etc`, gets a 400.
- **Sandboxed execution.** Prompt capture and regression tests *do* execute target code. They run in a temporary copy of the repo, with `.git`, venvs and `.env*` files excluded, and with a scrubbed environment that passes no API keys (`CASCADE_OFFLINE=1`). The process group is killed on timeout. This is **credential isolation, not an OS-level jail**: target code still has network and filesystem access.
- **Rate limiting.** A per-client-IP token bucket allows `RATE_LIMIT_PER_MINUTE` requests (default 60) and returns 429 with `Retry-After: 1`. `/api/health` and `OPTIONS` requests are exempt.
- **Request size.** Request bodies over 64 KiB get 413.
- **Host check.** `TrustedHostMiddleware` checks against `ALLOWED_HOSTS`; any other host gets 400. CORS allows only GET and POST, and only the `Content-Type` header.
- **Spend cap (live mode).** `DAILY_SPEND_CAP_USD` is a daily budget (default $10) that resets at UTC midnight. Before each call the worst-case cost is reserved; afterwards it is settled to the actual cost. A failed or cancelled call is charged its full reservation. Before a run starts, its projected cost is checked against the remaining budget. Models that are not in the catalog are refused. The cap is held in memory, so it applies per process.
- **Concurrency.** `MAX_CONCURRENT_RUNS` (default 2) benchmark runs at a time, and `BENCHMARK_CONCURRENCY` (default 4) model calls per run.
- **Honest data.** The backend never fabricates results. Missing recordings and failed calls are reported as errors, and the policy's `total_projected_cost_reduction_pct` is `null` when there is no baseline (the API's reduction fields report 0 in that case).
- **Conservative patching.** Calls that use streaming, tool calls or function calls are never rewritten. Every patched file must re-parse, and CRLF line endings and BOMs are preserved.

There is currently no hosted deployment. These limits apply to whatever instance you run.

---

## Team

Built for the **Nebius × NVIDIA Global AI Hackathon 2026**.

| Member | Role | Owned areas |
| :--- | :--- | :--- |
| **Saba** | Frontend Lead | Three-pane workbench UI (`frontend/`) |
| **Meenal Sinha** | Backend Lead & Integration Owner | FastAPI service, shared schemas, benchmark runner, optimizer, policy and patch generator, runtime wrapper (`backend/`) |
| **Pritam Singh** | AST Scanner & Agent Graph Lead | AST scanner, DAG builder, sample repo and fixtures (`backend/compiler/ast_scanner.py`, `dag_builder.py`, `tests/fixtures/`) |
| **Aditya** | Testing, Metrics & Docs Lead | Cost metrics, evaluator, regression runner, test suite, docs (`metrics.py`, `evaluator.py`, `regression_runner.py`, `tests/`, `README.md`) |
| **Salman Khurshid** | Spare Member & Overflow Backup | PR review, overflow backup for runner and runtime, friction logging |

---

## Docs

- [docs/architecture.md](docs/architecture.md): original architecture spec. Parts of it describe an earlier design; the code and this README take precedence.
- [docs/demo-scenarios.md](docs/demo-scenarios.md): demo script with curl examples and failure demos.
- [docs/test-report.md](docs/test-report.md): test results, per-module coverage, adversarial review notes.
- [backend_plan.md](backend_plan.md): backend plan, API contract and known limitations.

---

## Hackathon compliance

- **Event:** Nebius × NVIDIA Global AI Hackathon 2026
- **Track:** Track 1 — Coding & Agentic Engineering
- **Models (configured defaults, not yet confirmed with a live run):** NVIDIA Nemotron-3 Nano (30B-A3B), Nemotron-3.5 Lightning, Nemotron-3.5 Super-VL, Nemotron-3 Ultra (550B-A55B)
- **Infrastructure:** Nebius Token Factory (OpenAI-compatible API)
- **License:** MIT, see [LICENSE](LICENSE) in the repo root
- **Hosted demo:** none yet; run it locally with the Quickstart above
- **Demo video:** TODO, link to be added

---

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 CascadeRouter Contributors (Saba, Meenal Sinha, Pritam Singh, Aditya, Salman Khurshid).
