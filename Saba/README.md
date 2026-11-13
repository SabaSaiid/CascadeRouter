# CascadeRouter Architecture & Research Documentation

Welcome to the internal engineering specifications, benchmark analyses, and design notes for **CascadeRouter** — the Autonomous FinOps & Latency Compiler for LLM Architectures built for the Nebius × NVIDIA Hackathon.

## Overview

CascadeRouter analyzes multi-agent LLM systems, maps live data-dependency DAGs via static AST parsing without executing untrusted code, executes empirical benchmarks against Nebius Token Factory and NVIDIA hardware, optimizes model assignments for strict latency and cost constraints, and automatically applies verified atomic code patches.

## Documentation Index

- **[System Architecture](architecture-overview.md)**: Detailed breakdown of the 5-phase compiler pipeline (Scanner, DAG Builder, Benchmarking Engine, FinOps Optimizer, Atomic Patcher).
- **[Nebius Token Factory Guide](nebius-benchmarking-guide.md)**: Deep dive into empirical API benchmarking, Time-To-First-Token (TTFT), token generation throughput, and H100 GPU acceleration.
- **[NVIDIA Nemotron Evaluation](nvidia-nemotron-evaluation.md)**: Structured output validation, schema conformity, and reasoning benchmarks for `nvidia/Llama-3.1-Nemotron-70B-Instruct`.
- **[AST Static Scanner Specs](ast-scanner-specs.md)**: Zero-execution AST scanning algorithms across OpenAI, AsyncOpenAI, and LiteLLM call sites.
- **[FinOps Compiler Strategy](finops-compiler-strategy.md)**: Cost function formulations, Pareto optimization, and latency-budget routing algorithms.
- **[Multi-Agent Case Studies](multi-agent-case-studies.md)**: Real-world pipelines (Customer Support, RAG Synthesis, Document Processing) and financial impact analysis.
- **[Runtime Guardrails](runtime-guardrails.md)**: Fallback execution, circuit breaking, schema enforcement, and telemetry tracking.
- **[Latency Optimization](latency-optimization-notes.md)**: TTFT reduction techniques, streaming evaluation, prompt caching, and speculative routing.
- **[Deployment & Operations](deployment-and-operations.md)**: Production deployment guide for the workbench, CLI workflows, and CI/CD FinOps gating.
- **[Security & Compliance Architecture](security-and-compliance.md)**: Zero-execution static analysis guarantees, credential isolation, and audit controls.
- **[Telemetry & Metrics Specification](telemetry-and-metrics-spec.md)**: OpenTelemetry semantic conventions, Prometheus alerting rules, and Grafana dashboard layout.
- **[KV Cache Optimization](kv-cache-optimization.md)**: Block-level prefix caching mechanics, PagedAttention, and prefill latency acceleration.
- **[Speculative Decoding Analysis](speculative-decoding-analysis.md)**: Draft-target verification modeling using 8B draft and Nemotron-70B target.
- **[AST Scanner Edge Cases](edge-case-ast-handling.md)**: Dynamic keyword arguments, aliased imports, wrapper methods, and symbol propagation.
- **[Pareto Frontier Algorithms](pareto-frontier-algorithms.md)**: Multi-objective epsilon-constraint solvers and integer programming formulation.
- **[Circuit Breaker Patterns](circuit-breaker-patterns.md)**: Resilience state machines, exponential backoff with jitter, and provider failover.
- **[Empirical Benchmarking Methodology](benchmarking-methodology.md)**: Monotonic timer instrumentation, statistical IQR filtering, and Wilson confidence bounds.
- **[Developer Workbench Guide](developer-workbench-guide.md)**: Next.js/React studio, live ReactFlow DAG visualizer, and Monaco diff editor.
- **[Continuous FinOps in CI/CD](continuous-finops-ci-cd.md)**: GitHub Actions workflow, automated PR comments, and budget threshold gating.
- **[Structured Outputs with Nemotron](structured-outputs-nemotron.md)**: Grammar-guided decoding, DFA logit masking, and Pydantic validation benchmarks.
- **[Cost Attribution & Chargeback](cost-allocation-and-chargeback.md)**: Multi-tenant token metering, departmental quotas, and financial ERP integration.
- **[Troubleshooting & Diagnostics](troubleshooting-and-diagnostics.md)**: Operational triage decision trees, AST patch conflict recovery, and API diagnostics.
- **[REST API Reference & Contracts](api-reference-and-contracts.md)**: FastAPI endpoints, OpenAPI models, and WebSocket streaming telemetry contracts.
- **[Roadmap & Future Directions](roadmap-and-future-directions.md)**: Dynamic runtime arbitrage, FP8/INT4 quantization, and self-healing FinOps daemons.

## Core Design Principles

1. **Safety First**: Zero execution of untrusted repository code during scanning and static analysis.
2. **Empirical Measurement**: No synthetic guesswork; model routing decisions rely on empirical benchmarks over Nebius Token Factory endpoints.
3. **Deterministic Patching**: Atomic AST-guided code modifications with automated backups (`.bak`) and rollback capability.
4. **Targeted FinOps**: Squeezing maximum cost efficiency (up to 85% cost reduction) without compromising downstream generation quality.

---

## Model Selection Decision Matrix

| Workload Characteristic | Recommended Model | Primary Host Hardware | FinOps Rationale |
|---|---|---|---|
| Classification, Intent Triage, Extraction | `Meta-Llama-3.1-8B-Instruct` | Nebius Token Factory | Sub-80ms TTFT, $0.03 / 1M input tokens (91% cheaper) |
| Strict Schema JSON, Function Calling, Code | `nvidia/Llama-3.1-Nemotron-70B-Instruct` | NVIDIA H100 SXM5 | 99.7% schema compliance, 17% faster prefill than baseline 70B |
| Nuanced Synthesis, Empathy, Long Editorial | `Meta-Llama-3.1-70B-Instruct` | Nebius Token Factory | High semantic depth, balanced open weights performance |

---

## Technical Glossary

- **TTFT (Time-To-First-Token)**: Latency from request transmission until receipt of the first streamed SSE chunk.
- **Pareto Frontier**: Set of non-dominated routing configurations where cost cannot be lowered without increasing latency or decreasing schema quality.
- **Byte-Span Replacement**: Precise slice editing of source code using exact character offsets from the AST, preserving untargeted syntax.
- **Prefix Caching**: Server-side KV cache retention on Nebius H100 clusters enabling accelerated prefill for recurrent prompt prefixes.

