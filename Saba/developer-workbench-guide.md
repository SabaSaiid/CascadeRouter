# Developer Workbench Guide & UI Architecture

## 1. Interactive Studio Overview

The CascadeRouter Developer Workbench provides an interactive, visual interface for developers to inspect their repository’s multi-agent LLM call sites, visualize data-flow DAGs, configure FinOps optimization criteria, preview atomic AST patches, and trigger one-click commits.

```
  ┌─────────────────────────────────────────────────────────────┐
  │                   CascadeRouter Workbench                   │
  ├───────────────────┬─────────────────────────────────────────┤
  │ Call Site Explorer│ Interactive DAG Canvas (ReactFlow)      │
  │ ├─ triage.py:24   │   [User Input]                          │
  │ ├─ extract.py:45  │         │                               │
  │ └─ summary.py:88  │         ▼                               │
  ├───────────────────┤   (8B: Triage) ──► (Nemotron: Extract)  │
  │ Pareto Optimizer  │                         │               │
  │ [●] FinOps Target │                         ▼               │
  │ [ ] Latency SLA   │                  (8B: Summary)          │
  ├───────────────────┴─────────────────────────────────────────┤
  │ Unified Diff & Patch Preview (Monaco Editor)                │
  │ - client.chat.completions.create(model="gpt-4o")            │
  │ + client.chat.completions.create(model="Meta-Llama-3.1-8B") │
  └─────────────────────────────────────────────────────────────┘
```

---

## 2. Frontend Architecture & State Management

The frontend is constructed using modern web primitives:
- **Next.js & React 18**: Modular component tree with server-side rendering for lightning-fast initial load.
- **ReactFlow DAG Visualizer**: Dynamically renders nodes representing discovered LLM call sites, edge connections representing data dependencies, and color-coded provider badges.
- **Monaco Editor Diff Engine**: Displays syntax-highlighted side-by-side diffs showing precise AST byte-span edits before touching disk.
- **WebSocket Live Telemetry Stream**: Connects to the FastAPI backend (`backend/api/`) to stream real-time token throughput and TTFT gauges during live benchmark runs.

---

## 3. Core Workbench Workflows

### Phase 1: Repository Discovery
1. The developer inputs the local path or selects a branch.
2. The backend initiates the zero-execution AST scanner (`ScanService`).
3. Discovered call sites populate the left-hand navigation pane with detected models, token budgets, and line numbers.

### Phase 2: Live Benchmark Execution
1. Select one or more target endpoints (Nebius Llama-3.1-8B, Nebius Llama-3.1-70B, NVIDIA Nemotron-70B).
2. Click **Run Benchmark**. The system dispatches synthetic test payloads to measure TTFT and token generation throughput.
3. The live streaming HUD graphs real-time SSE chunks and latencies.

### Phase 3: Pareto Frontier Optimization
1. Move the **FinOps vs. Latency Slider** to choose between Ultra-Budget, Balanced, and Max-Accuracy presets.
2. The optimizer recalculates model assignments across all DAG nodes instantly.
3. Projected annual savings and P95 latency figures update in real time.

### Phase 4: Patch Inspection & Application
1. Click **Preview Patches**. The Monaco diff editor displays the exact line and character alterations.
2. Review the automated AST validation report (`patch_validator.py` confirms 100% AST isomorphism).
3. Click **Apply Patches**. Changes are atomically committed to the working tree with backup `.bak` snapshots.
