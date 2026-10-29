# CascadeRouter: Demo Scenarios

A 3-minute walkthrough of the bundled sample app (`tests/fixtures/sample_repo`). It's a support-triage agent that sends three steps to the 550B Ultra model.

## 0. Setup (before the demo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # put NEBIUS_API_KEY in .env
```

There are two honest ways to run it:

| Mode | `.env` | What the judges see |
| :--- | :--- | :--- |
| **Live** | `DATA_SOURCE_MODE=live`, `RECORD_RUNS=true` | Real Nebius calls. Each response is also saved under `recordings/`. |
| **Recorded** | `DATA_SOURCE_MODE=recorded` | The real responses saved from a live run, replayed with no cost and no network. |

Do one live run before the demo so `recorded` mode has data. If a request was never recorded, recorded mode reports it as a failed cell. It never makes a number up.

Start everything with `./start.sh` (backend on `127.0.0.1:8000`, UI on `localhost:5173`).

## 1. Scan (~30 s)

Click **Analyze Repository**, or call it directly:

```bash
curl -s -X POST localhost:8000/api/scan -H 'Content-Type: application/json' \
  -d '{"repository_path": "tests/fixtures/sample_repo"}' | jq '.nodes[] | {node_id, current_model, prompt_reference}'
```

Expected: 3 nodes, all on `nvidia/Nemotron-3-Ultra-550b-a55b`.
- `node_classify_customer_intent`: JSON with an enum schema
- `node_extract_ticket_metadata`: `response_format=json_object`
- `node_generate_support_resolution`: free text, `max_tokens=1024`

The DAG shows classify → extract → generate.

Talking point: the scan is pure `ast` analysis. The target code is never imported or run.

## 2. Benchmark (~60 s)

Click **Run Nemotron Benchmark Matrix** (`POST /api/benchmark {node_ids}`, then poll `GET /api/runs/{run_id}`).

What happens:
1. **Prompt capture.** Each node's function runs once per case in `cascade_cases.yaml`, inside a temporary sandbox with no API key. A capturing stand-in for the client records the exact request the app would send (f-strings and message history included) and stops before any network call.
2. **Benchmark.** 6 cases × 4 Nemotron tiers = 24 calls, run concurrently with a cap. Each call records real input/output tokens, total latency and time to first token.
3. **Evaluation.** Fixed rules, no LLM judge: JSON parse, required fields, schema types and enums, agreement with the labelled answers, and required phrases for free text.

Talking point: the matrix shows Nano and Lightning passing classification and extraction at about 1/16 of Ultra's cost, but failing the free-text resolution. Super-VL is the cheapest tier that passes there.

## 3. Optimize & patch (~45 s)

Click **Generate Patch & Policy** (`POST /api/optimize {run_id, quality_threshold: 0.92}`).

- **Decision per node:** the cheapest model with quality ≥ 0.92 that passes all hard checks. Models within 2% on cost are tie-broken on latency. The fallback is the next tier up.
- **`.cascaderouter.yaml`:** the routing policy plus the measured evidence (costs, latency and quality) behind it.
- **Unified diff:** each optimized call `client.chat.completions.create(` becomes `cascade_router.dispatch(node_id=..., client=client,`. All original arguments are kept.

## 4. Regression (~20 s)

The patched copy of the repo runs its own `pytest` suite in a sandbox: no credentials, 30 s timeout, runtime bundled in as `cascaderouter.py`. All 6 tests pass. A patch only counts as verified when the suite actually ran and passed.

## 5. Runtime fallback (~15 s)

`cascaderouter.CascadeRouter.load(__file__)` reads the policy:
- It calls Nano first. If the reply isn't valid JSON or misses a required field, it retries once on the fallback.
- If the fallback fails too, it returns the primary reply, so routing never makes the app worse than before.
- If the policy file is missing, every call passes through unchanged.

## Failure demos (optional)

| Show | How | Expected |
| :--- | :--- | :--- |
| No fabricated data | `DATA_SOURCE_MODE=recorded` with an empty `recordings/` | Cells are `failed` with "no recording for this request", and there's no recommendation |
| Spend cap | `DAILY_SPEND_CAP_USD=0` in live mode | `POST /api/benchmark` returns 429 "Daily spend cap reached" |
| Path safety | scan `/etc` | 400 "outside the allowed scan roots" |
| No key | live mode without `NEBIUS_API_KEY` | 503 with a clear message |
