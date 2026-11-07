# CascadeRouter Architectural Deep Dive

CascadeRouter is designed as an autonomous compiler and optimizer for multi-agent LLM systems. This document outlines the inner mechanics of each subsystem in the compilation pipeline.

## System Architecture Pipeline

The compiler operates across five discrete phases:

```
+--------------------------------------------------------------------------+
| Phase 1: Static AST Analysis (Zero Untrusted Code Execution)             |
|   - Python `ast.parse` walks target codebase                             |
|   - Extracts Call sites for OpenAI, AsyncOpenAI, LiteLLM                 |
|   - Captures prompt templates, model strings, sampling parameters        |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
| Phase 2: Live Dependency DAG Inference                                   |
|   - Tracks variable assignments and argument dependencies                |
|   - Maps sequential and fan-out agent workflows                          |
|   - Identifies critical path latency bottlenecks                         |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
| Phase 3: Empirical Hardware Benchmarking                                 |
|   - Nebius Token Factory live API client (`/v1/chat/completions`)        |
|   - High-precision telemetry: TTFT, token throughput (tokens/sec)        |
|   - Real-world evaluation against NVIDIA H100 SXM5 infrastructure        |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
| Phase 4: FinOps Cost & Latency Optimization Engine                       |
|   - Multi-objective Pareto frontier solver                               |
|   - Enforces user-defined SLA targets and schema pass rates              |
|   - Down-selects high-cost frontier calls to calibrated 8B/70B models    |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
| Phase 5: Verified Atomic Code Patching                                   |
|   - Computes byte-exact AST source replacements                          |
|   - Emits unified diff proposals and safe `.bak` backups                 |
|   - Post-patch AST validation prevents syntax and execution regressions  |
+--------------------------------------------------------------------------+
```

## 1. Static AST Scanner

The static scanner inspects Python files without triggering runtime imports. Traditional dynamic profiling executes module-level scripts, which poses security vulnerabilities and side effects when parsing user code. 

CascadeRouter leverages the standard library `ast` module with custom node visitors:
- **`OpenAICallVisitor`**: Detects instances of `client.chat.completions.create(...)`, async variants, and functional wrappers.
- **`LiteLLMVisitor`**: Matches `litellm.completion` and `litellm.acompletion` invocations.
- **Literal Evaluator**: Resolves string literals, dictionary mappings, and formatted strings to identify the hardcoded model parameters (e.g., `model="gpt-4o"`).

## 2. Dependency Graph Inference

Multi-step pipelines commonly feature producer-consumer relationships:
- Node 1: Intent Triage (outputs category string or JSON).
- Node 2: Document Context Retrieval (takes category as query filter).
- Node 3: Synthesizer (ingests context and user prompt to draft response).

By tracking symbol definitions (`ast.Assign`, `ast.Name`, and argument references), CascadeRouter generates a directed acyclic graph (DAG). This DAG reveals which nodes are latency-critical and which can tolerate minor throughput differences.

## 3. Empirical Benchmarking Engine

Rather than relying on theoretical FLOPS or outdated static cost sheets, CascadeRouter issues live test payloads to Nebius Token Factory:
- Sends sanitized canary prompts or sample task payloads.
- Records Time to First Token (TTFT) via chunk streaming.
- Calculates true token generation velocity (decode tokens / second).
- Records dollar expenditures according to actual token count multiplied by model pricing tiers.

## 4. FinOps Routing Optimizer

The optimization engine evaluates candidate models from the Nebius catalog:
- `meta-llama/Meta-Llama-3.1-8B-Instruct`
- `meta-llama/Meta-Llama-3.1-70B-Instruct`
- `nvidia/Llama-3.1-Nemotron-70B-Instruct`

Optimization objectives include:
- **Minimizing Cost**: Identifying nodes where 8B models achieve identical accuracy or classification fidelity at 90%+ cost reduction.
- **Maximizing Schema Compliance**: Allocating NVIDIA Nemotron-70B to complex JSON parsing nodes where structural errors break downstream logic.
- **Enforcing Latency Budgets**: Ensuring the total critical-path latency remains within the user's p95 SLA.

## 5. Atomic Code Patcher

Once the user approves the optimization plan, the patcher applies AST-guided string replacements:
- Preserves exact code formatting, indentation, and docstrings.
- Generates a timestamped `.bak` file for instantaneous recovery.
- Runs an immediate AST round-trip compilation check on the patched file to guarantee syntactical integrity.

### Patch Safety & Rollback Lifecycle

```
[ Optimization Plan Approved ]
              |
              v
[ Step 1: Pre-patch AST Validation ] ---> (Fails) ---> [ Abort Operation ]
              |
              v (Pass)
[ Step 2: Create .bak Backup ] (e.g., pipeline.py.20261107.bak)
              |
              v
[ Step 3: Compute Exact Byte Span ]
              |
              v
[ Step 4: Apply Atomic Write ]
              |
              v
[ Step 5: Post-patch AST Verification ]
      |                      |
   (Valid)               (Invalid)
      |                      |
      v                      v
[ Emit Success ]    [ Auto-Rollback from .bak & Raise Safety Alert ]
```

### Byte-Span Replacement Mechanics

Rather than unparsing the full AST back to source code (which discards formatting, comments, and spacing), CascadeRouter performs surgery strictly at the identified slice boundaries:

```python
def apply_span_replacement(original_code: str, start_byte: int, end_byte: int, replacement: str) -> str:
    """Replaces a targeted slice while preserving all surrounding code untouched."""
    return original_code[:start_byte] + replacement + original_code[end_byte:]
```

This guarantees 100% preservation of comments, inline type annotations, and codebase styling.

