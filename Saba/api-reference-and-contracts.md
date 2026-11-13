# Internal REST API Reference & Data Contracts

## 1. Core Endpoints Overview

The CascadeRouter daemon exposes a high-performance REST API built with FastAPI (`backend/main.py`), supporting automated repository analysis, live benchmarking, optimization synthesis, and patch execution.

| Endpoint | Method | Description |
|---|---|---|
| `/api/scan` | `POST` | Triggers zero-execution AST scan of local or remote repository paths. |
| `/api/benchmarks/run` | `POST` | Initiates asynchronous live benchmarking job across selected endpoints. |
| `/api/benchmarks/ws/{job_id}` | `WebSocket` | Real-time SSE streaming of token generation and TTFT telemetry. |
| `/api/optimize` | `POST` | Solves Pareto optimization problem and returns recommended routing policy. |
| `/api/patches/preview` | `POST` | Generates unified git diffs showing planned byte-span edits. |
| `/api/patches/apply` | `POST` | Atomically commits patches to filesystem with automated rollback snapshots. |

---

## 2. Request & Response Payloads

### `POST /api/scan`

**Request Payload:**
```json
{
  "target_path": "backend/",
  "exclude_patterns": ["tests/*", "venv/*"],
  "include_dynamic_calls": true
}
```

**Response Payload (`ScanResponse`):**
```json
{
  "status": "success",
  "total_files_scanned": 18,
  "call_sites_found": 5,
  "call_sites": [
    {
      "id": "site_01",
      "file_path": "backend/agents/triage.py",
      "line_number": 24,
      "col_offset": 32,
      "end_col_offset": 40,
      "current_model": "gpt-4o",
      "context_window_tokens": 1280,
      "has_json_schema": false
    }
  ]
}
```

---

### `POST /api/optimize`

**Request Payload (`OptimizationRequest`):**
```json
{
  "scan_id": "scan_8821",
  "sla_profile": "balanced",
  "max_critical_path_latency_ms": 750.0,
  "min_schema_accuracy": 0.98,
  "enabled_providers": ["nebius", "nvidia"]
}
```

**Response Payload:**
```json
{
  "pareto_solutions": [
    {
      "solution_id": "sol_optimal",
      "assigned_models": {
        "site_01": "Meta-Llama-3.1-8B-Instruct",
        "site_02": "nvidia/Llama-3.1-Nemotron-70B-Instruct"
      },
      "projected_cost_per_1k_runs_usd": 0.38,
      "projected_savings_percentage": 65.5,
      "estimated_p95_latency_ms": 620.0
    }
  ]
}
```

---

## 3. WebSocket Streaming Protocol (`/api/benchmarks/ws/{job_id}`)

Clients receive streaming JSON frames updating live benchmark execution progress:

```json
{
  "event": "token_chunk",
  "job_id": "bench_991",
  "model_id": "nvidia/Llama-3.1-Nemotron-70B-Instruct",
  "token_index": 42,
  "elapsed_ms": 312.4,
  "instantaneous_tps": 78.5,
  "is_complete": false
}
```
