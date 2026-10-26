# CascadeRouter IDE — Architecture & Technical Specification

> **Autonomous FinOps & Latency Compiler for LLM Architectures**  
> *Nebius × NVIDIA Global AI Hackathon 2026 · Track 1 (Coding & Agentic Engineering)*

---

## 1. Executive Summary

AI engineering teams routinely over-provision models—defaulting to heavyweight 70B+ or 550B frontier models for mundane tasks like schema extraction, summarization, classification, or deterministic formatting. This results in massive cloud compute bills and high token-to-first-token (TTFT) / total latency overhead.

**CascadeRouter IDE** solves this by acting as an **Autonomous FinOps & Latency Compiler**:
1. Statically scans Python AI repositories using AST analysis to discover LLM invocation sites and call graphs without executing arbitrary code.
2. Benchmarks those prompts across **NVIDIA Nemotron** model tiers hosted on **Nebius Token Factory** measuring exact tokens, latency, TTFT, and determinism.
3. Optimizes node assignments to the lowest-cost model meeting strict quality thresholds ($\ge 0.92$).
4. Emits a deterministic routing policy (`.cascaderouter.yaml`) alongside a safe, reviewable unified code patch.
5. Verifies safety through sandbox regression test execution.
6. Presents the entire lifecycle inside a three-pane developer workbench UI with live/recorded/mock telemetry.

---

## 2. System Architecture & End-to-End Pipeline

```
+-----------------------------------------------------------------------------------------+
|                                    TARGET REPOSITORY                                    |
|              (e.g., tests/fixtures/sample_repo - Python AI Agent Codebase)              |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 1] AST SCANNER & DAG BUILDER (Pritam)                                            |
| - ast.parse() with safe visitor                                                         |
| - Detects OpenAI SDK / Nemotron calls, prompt templates, output schema requirements     |
| - Builds workflow dependency graph                                                      |
| Output: ScanResult (Nodes, Locations, Graph Edges)                                      |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 2] BENCHMARK SHADOW RUNNER & EVALUATOR (Meenal & Aditya)                         |
| - Bounded concurrent inference against Nebius Token Factory                             |
| - Benchmarks across NVIDIA Nemotron tiers (Nano, Lightning, Super-VL, Ultra)             |
| - Evaluator runs schema validation, field completeness, task assertions                 |
| - Metrics calculates TTFT, median/p95 latency, input/output tokens, and exact cost ($)  |
| Output: BenchmarkMatrix (Per-node, per-model scores, latency & cost)                     |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 3] FINOPS ROUTER OPTIMIZER (Meenal)                                              |
| - Applies objective: min(cost) s.t. Quality >= Threshold (0.92) & Hard Assertions Pass  |
| - Identifies fallback triggers & models                                                 |
| - Generates .cascaderouter.yaml routing configuration                                    |
| Output: OptimizationPlan (Selected models, projected savings, fallback policies)        |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 4] PATCH GENERATOR & REGRESSION RUNNER (Meenal & Aditya)                         |
| - Synthesizes unified git patch replacing hardcoded models with CascadeRouter hooks    |
| - Isolated sandbox runs pytest against sample repo regression suite                     |
| - Verifies zero semantic regression                                                     |
| Output: PatchResult (Diff, Pass/Fail status, Regression logs)                            |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 5] THREE-PANE WORKBENCH UI (Saba)                                                |
| --------------------------------------------------------------------------------------- |
| Pane 1: Repository & AST Graph | Pane 2: Benchmark Matrix      | Pane 3: Diff & Policy  |
| - Discovered LLM nodes         | - Live Nemotron metrics       | - Baseline vs Opt      |
| - Code location & signatures   | - Cost ($/1M), Latency, TTFT  | - Unified Git Diff     |
| - DAG visualization            | - Pass/Fail Quality Badges    | - .cascaderouter.yaml  |
|                                | - Live / Recorded / Mock mode | - Regression Status    |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| [STAGE 6] RUNTIME CASCADE ROUTER (Meenal & Salman)                                      |
| - Lightweight zero-overhead Python wrapper                                              |
| - Dispatches to optimized tier (e.g., Nemotron Nano)                                    |
| - Automatically escalates to Ultra tier if validation assertion fails at runtime        |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Verified Model Catalog & Nebius Token Factory Economics

Rates verified against Nebius Token Factory (as of October 26, 2026):

| Tier | Model ID | Input ($/1M tok) | Output ($/1M tok) | Target Workloads |
| :--- | :--- | :---: | :---: | :--- |
| **Efficient** | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | **$0.06** | **$0.24** | JSON extraction, classification, sentiment, formatting |
| **Efficient (Alt)** | `nvidia/Nemotron-3_5-Lightning` | **$0.06** | **$0.24** | Ultra-low-latency streaming, quick summarization |
| **Balanced** | `nvidia/Nemotron-3.5-Super-VL` | **$0.30** | **$0.90** | Complex logic, multi-turn dialogue, multimodal, code analysis |
| **Powerful** | `nvidia/Nemotron-3-Ultra-550b-a55b` | **$1.00** | **$3.00** | Heavy reasoning, frontier generation, high-ambiguity synthesis |

### FinOps Cost Formulation (`backend/compiler/metrics.py`)
```python
estimated_cost = (
    (input_tokens / 1_000_000) * input_price_per_million
    + (output_tokens / 1_000_000) * output_price_per_million
)

cost_savings_pct = (
    ((baseline_cost - optimized_cost) / baseline_cost) * 100.0
    if baseline_cost > 0 else 0.0
)
```

---

## 4. Shared Data Contracts (`backend/schemas.py` & `frontend/src/types.ts`)

The shared Pydantic schemas in `backend/schemas.py` define the single source of truth:

```python
# Core conceptual types:
class LLMNode(BaseModel):
    node_id: str
    file_path: str
    line_number: int
    current_model: str
    call_signature: str
    prompt_reference: Optional[str]
    expected_schema: Optional[dict]

class ScanResult(BaseModel):
    repository_path: str
    nodes: list[LLMNode]
    graph_edges: list[tuple[str, str]]
    timestamp: str

class BenchmarkMetric(BaseModel):
    model_id: str
    tier: str
    input_tokens: int
    output_tokens: int
    total_latency_ms: float
    time_to_first_token_ms: Optional[float]
    estimated_cost_usd: float
    quality_score: float
    passes_validation: bool
    validation_errors: list[str] = []

class OptimizationDecision(BaseModel):
    node_id: str
    baseline_model: str
    recommended_model: str
    fallback_model: str
    cost_reduction_pct: float
    latency_reduction_pct: float
    status: str  # "optimized" | "inconclusive" | "baseline_retained"
    policy_yaml: str
    patch_diff: str
    regression_passed: bool
```

---

## 5. Security & Safety Invariants

1. **No Code Execution During Scanning**: Pritam's AST scanner strictly relies on Python's native `ast` module. Scanned code is never imported, run, or evaluated.
2. **Hermetic Regression Sandbox**: Aditya's regression runner executes tests in isolated temporary directories (`tempfile.mkdtemp()`) with strict execution timeouts (30s) and stripped environment variables (no access to production credentials or host secrets).
3. **Deterministic Patch Verification**: Any code patch generated must pass both static parse validation and repository regression tests before being marked verified.
4. **Key Isolation**: API keys remain strictly confined to backend `.env`. They are never passed to the frontend, exposed in API logs, or committed to Git.
