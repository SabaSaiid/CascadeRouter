# ⚡ CascadeRouter
### Autonomous FinOps & Latency Compiler for LLM Architectures
**Built for the Nebius × NVIDIA Hackathon 2026**

[![Frontend Tests](https://img.shields.io/badge/Frontend%20Tests-117%2F117%20Passing-34D399?style=flat-square)](frontend/tests/)
[![Backend Tests](https://img.shields.io/badge/Backend%20Pytest-1299%20Passing-34D399?style=flat-square)](tests/)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict%206.0-4D85FF?style=flat-square)](frontend/tsconfig.json)
[![Hardware](https://img.shields.io/badge/Inference-Nebius%20Token%20Factory%20%C3%97%20NVIDIA%20H100-76B900?style=flat-square)](https://nebius.com/)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

> CascadeRouter statically parses Python AI codebases, infers live LLM data-dependency DAGs without running untrusted code, executes empirical benchmarks against **Nebius Token Factory** and **NVIDIA Nemotron**, optimizes model selection for cost and latency, and applies verified atomic code patches with zero hallucinations.

---

## 🎯 The Problem
Enterprise multi-agent architectures (customer support, data synthesis, RAG pipelines) chain multiple LLM calls. Developers typically hardcode monolithic 70B+ or frontier models (`gpt-4o`) across every step. 

- **Result**: Companies burn **70% to 85% of their inference budget** using expensive frontier models for routine triage, intent routing, and JSON extraction.
- **Risk**: Manually refactoring model names in production code risks syntax regressions, prompt schema mismatches, and downtime.

---

## 💡 The Solution
CascadeRouter acts as an **autonomous FinOps compiler** for your LLM code:

1. **Zero-Execution Static AST Scanner**: Parses Python call sites (`OpenAI`, `AsyncOpenAI`, `LiteLLM`) without importing or executing untrusted code.
2. **Data-Dependency Graph Inference**: Tracks lexical variable bindings between producers and consumers to build a live visual dependency DAG.
3. **Nebius Token Factory Benchmarking**: Measures empirical time-to-first-token (TTFT) via Server-Sent Events, token generation throughput, schema validation, and real dollar costs on NVIDIA GPUs.
4. **Evidence-Based Routing Optimizer**: Selects the optimal model for each step based on verified pass rates, strict schema compliance, and cost efficiency.
5. **Atomic 1-Click Code Patching**: Generates exact byte-span replacement proposals and patches your repository with automated `.bak` backups and rollback safety.

---

## 🏆 Nebius × NVIDIA Integration

CascadeRouter specifically unlocks the speed and economics of **Nebius Token Factory** and **NVIDIA GPUs**:

| Model | Hosted On | Role in Pipeline | In/Out per 1M Tokens | Observed Latency | FinOps Impact |
|---|---|---|---|---|---|
| `meta-llama/Meta-Llama-3.1-70B-Instruct` | **Nebius Token Factory** | Complex synthesis baseline | $0.35 / $0.40 | ~295ms | Baseline cost |
| `nvidia/Llama-3.1-Nemotron-70B-Instruct` | **Nebius on NVIDIA H100** | Structured JSON & deep reasoning | $0.35 / $0.40 | ~245ms | **17% faster**, strict JSON compliance |
| `meta-llama/Meta-Llama-3.1-8B-Instruct` | **Nebius Token Factory** | High-speed triage & classification | $0.03 / $0.09 | ~78ms | **91% cost drop**, 3.7x lower latency |

- **Live Benchmark Engine**: Directly connects to `https://api.tokenfactory.nebius.com/v1` (or `https://api.studio.nebius.ai/v1`) with streaming TTFT capture when `NEBIUS_API_KEY` is provided, with calibrated high-fidelity live emulation fallback for offline testing.
- **Deterministic FinOps Ledger**: Computes exact dollar expenditures using official Nebius Token Factory pricing.

---

## 🚀 60-Second Quickstart

### 1. Install & Launch the Workbench
```bash
git clone https://github.com/SabaSaiid/CascadeRouter.git
cd CascadeRouter

# Install backend & frontend dependencies
pip install -r requirements.txt
npm install --prefix frontend

# Launch services
bash start.sh
```
`start.sh` automatically provisions local benchmark assets, starts the FastAPI backend on port 8000, and launches the Vite IDE on port 5173.

*(Optional)* To benchmark against live Nebius cloud endpoints:
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
bash start.sh
```

### 2. Walk Through the 1-Click Demo Journey
1. Open **`http://localhost:5173`** in your browser to view the **Overview Home Screen**.
2. Click **"Try the sample agent"** (instantly loads `examples/customer_support_agent`), or click **"Scan my own repository"**.
3. View the **Visual Agent Graph** — see the 3-step chained agent pipeline with live data-dependency edges.
4. Filter or sort findings in the calls pane, select a node, click **"Use Nebius / NVIDIA Defaults"**, and click **"Submit local benchmark job"**.
5. Watch the live execution progress bar measure TTFT and token rates across models.
6. Under **3. Evidence-based optimization**, click **"Request backend optimization"** to see verified cost savings.
7. Under **4. Proposal review**, inspect the exact AST byte diff and YAML policy, then click **"Apply Verified Patch to Codebase"** with automated `.bak` backups!
8. Open the **Analytics Dashboard** via the sidebar to experiment with the **Interactive ROI Impact Slider** and review enterprise FinOps projections.

---

## 📁 Project Layout & Architecture

| Path | Responsibility |
| --- | --- |
| [backend/main.py](backend/main.py) | App factory and loopback CLI |
| [backend/compiler/](backend/compiler/) | AST static analysis, DAG builder, evidence metrics, cost selector, policy generator, and patch validator |
| [backend/runtime/](backend/runtime/) | Production runtime router, execution guardrails, and cascade fallback |
| [backend/services/live_benchmark.py](backend/services/live_benchmark.py) | Nebius Token Factory streaming API client and performance benchmark engine |
| [backend/services/default_assets.py](backend/services/default_assets.py) | Auto-provisioning local benchmark registries and Nebius Token Factory pricing |
| [examples/customer_support_agent/](examples/customer_support_agent/) | Showcase multi-agent customer support pipeline with chained data-dependency flow |
| [frontend/src/](frontend/src/) | React 19 IDE with interactive SVG Agent Graph canvas, ROI calculator, and themes |
| [tests/](tests/) | Comprehensive test suite (1,299 backend tests + 117 frontend tests) |
| [docs/](docs/) | Formal API contracts, benchmark specifications, and audit records |
| [Saba/](Saba/README.md) | In-depth engineering research, Wilson score statistics, TTFT latency anatomy, and Nemotron evaluation |

---

## 🧪 Testing & Validation

```bash
# Backend test suite (1,299 tests across compiler, security, and integration)
PYTHONPATH=. pytest tests/

# Frontend test suite (117 native TypeScript tests)
npm test --prefix frontend

# Typecheck and linting
npm run typecheck --prefix frontend
npm run lint --prefix frontend

# Production build
npm run build --prefix frontend
```

For detailed specifications, see the [Architecture Deep Dive](Saba/README.md), [API contract](docs/api-contract.md), [runtime routing](docs/runtime-routing.md), [offline benchmarks](docs/offline-benchmark.md), and [security model](SECURITY.md).

---

## 📄 License

MIT. See [LICENSE](LICENSE) for terms and contributor notices.
