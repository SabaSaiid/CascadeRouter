> **Current integration (Phase 4.10): offline local backend only.** The original
> hackathon vision below is historical, not the implemented setup or safety
> contract. There are no hosted provider calls, automatic source edits, or runtime
> regression claims in this branch. Start with [local frontend setup](frontend/README.md),
> [implemented flows](docs/frontend-integration.md), and
> [static validation limitations](docs/patch-validation.md). Missing or unapproved
> benchmark evidence remains unavailable; demonstration data is explicitly labeled.
> [Acceptance results and unresolved release gates](docs/phase410-acceptance.md)
> distinguish passing local checks from unverified production/browser behavior.

# CascadeRouter IDE

### *Autonomous FinOps & Latency Compiler for LLM Architectures*

[![Hackathon](https://img.shields.io/badge/Nebius%20%C3%97%20NVIDIA-Global%20AI%20Hackathon%202026-76B900?logo=nvidia&logoColor=white)](https://devpost.com)
[![Track](https://img.shields.io/badge/Track-1%3A%20Coding%20%26%20Agentic%20Engineering-blue)](https://devpost.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory-8A2BE2)](https://nebius.ai)

---

## ⚡ Overview

**CascadeRouter IDE** is an autonomous FinOps and latency compiler designed to eliminate LLM over-provisioning in modern Python AI agent codebases. 

In production AI applications, developers frequently default to expensive 70B+ or 550B frontier models for straightforward tasks such as schema extraction, classification, sentiment analysis, or deterministic formatting. This practice causes **10x–50x cost inflation** and unacceptable token-to-first-token (TTFT) latency spikes.

CascadeRouter statically inspects your repository, benchmarks your exact prompt nodes across **NVIDIA Nemotron** model tiers via **Nebius Token Factory**, mathematically selects the lowest-cost model that satisfies quality and schema requirements ($\ge 0.92$), and automatically generates:
1. A **declarative routing policy** (`.cascaderouter.yaml`)
2. A **unified, reviewable Git code patch**
3. An **isolated regression test validation** ensuring zero semantic regressions
4. A **runtime fallback wrapper** that escalates to frontier models dynamically if runtime validation fails

All workflows are presented in a real-time, interactive **three-pane developer workbench UI**.

---

## 🏗️ Architecture & Pipeline

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           TARGET PYTHON AI CODEBASE                            │
│                 (e.g., tests/fixtures/sample_repo with LLM calls)              │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  [1] AST Static Scanner & DAG Builder                                          │
│  - Parses codebase using Python's native `ast` module (safe, zero code exec)  │
│  - Extracts call sites, prompt references, model IDs, expected schemas         │
│  - Emits normalized LLM nodes and directed workflow graph                      │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  [2] Nebius Token Factory Benchmark Runner & Evaluator                         │
│  - Queries NVIDIA Nemotron model tiers concurrently with bounded concurrency   │
│  - Measures exact input/output tokens, wall-clock latency, and TTFT            │
│  - Deterministic evaluation: JSON schema conformance, required fields, checks  │
│  - Calculates FinOps cost ($) using verified Nebius per-million token rates    │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  [3] FinOps Router Optimizer                                                   │
│  - Objective: min(Cost) s.t. Quality >= Threshold (0.92) & Hard Checks Pass    │
│  - Generates `.cascaderouter.yaml` policy & unified git code patch             │
│  - Configures runtime fallback escalation paths                                │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  [4] Sandbox Regression Runner                                                 │
│  - Clones sample repo to isolated temp directory (no credentials, 30s timeout) │
│  - Applies patch and executes test suite (`pytest`) to ensure zero regression  │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  [5] Three-Pane Developer Workbench UI                                         │
│  - Left: Repository Analysis, Discovered LLM Nodes & Agent DAG                 │
│  - Center: Benchmark Matrix (Nebius tokens, latency, cost $, pass/fail badges) │
│  - Right: FinOps Comparison, Unified Diff, Policy YAML & Regression Status     │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 💰 Verified NVIDIA Nemotron Models on Nebius Token Factory

Rates verified against Nebius Token Factory on **October 26, 2026**:

| Tier | Model ID | Input ($/1M) | Output ($/1M) | Characteristics & Workload Fit |
| :--- | :--- | :---: | :---: | :--- |
| **Efficient** | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | **$0.06** | **$0.24** | Extremely lightweight, low latency, ideal for structured JSON extraction & classification |
| **Efficient (Alt)** | `nvidia/Nemotron-3_5-Lightning` | **$0.06** | **$0.24** | Ultra-fast token generation, rapid summarization & intermediate agent steps |
| **Balanced** | `nvidia/Nemotron-3.5-Super-VL` | **$0.30** | **$0.90** | Multimodal reasoning, complex synthesis, high-accuracy structured tasks |
| **Powerful** | `nvidia/Nemotron-3-Ultra-550b-a55b` | **$1.00** | **$3.00** | Frontier reasoning & code generation; acts as final runtime fallback |

### FinOps Cost Equation (`backend/compiler/metrics.py`)
$$\text{Cost} = \left(\frac{\text{Tokens}_{\text{in}}}{10^6} \times \text{Price}_{\text{in}}\right) + \left(\frac{\text{Tokens}_{\text{out}}}{10^6} \times \text{Price}_{\text{out}}\right)$$

$$\text{Savings \%} = \frac{\text{Cost}_{\text{baseline}} - \text{Cost}_{\text{optimized}}}{\text{Cost}_{\text{baseline}}} \times 100\%$$

---

## 🖥️ The Three-Pane Developer Workbench

The frontend interface (`frontend/src/`) delivers a high-density, mission-control developer experience:

```
+-----------------------------------+-----------------------------------+-----------------------------------+
|  1. REPOSITORY ANALYSIS           |  2. BENCHMARK MATRIX              |  3. OPTIMIZATION & DIFF           |
|                                   |                                   |                                   |
|  * Loaded repo: sample_repo       |  * Model Comparison Matrix        |  * Baseline vs. Recommended       |
|  * Discovered LLM Calls:          |    - Nano-30B:    $0.00012 | PASS |    Ultra-550b  -> Nano-30B        |
|    - [app.py:42] classify_intent  |    - Lightning:   $0.00011 | PASS |  * Cost Reduction:      -88.4%    |
|    - [app.py:89] extract_entities |    - Super-VL:    $0.00062 | PASS |  * Latency Reduction:   -62.1%    |
|    - [app.py:150] synthesize_plan |    - Ultra-550b:  $0.00284 | PASS |  * Quality Score:       0.96      |
|  * Interactive DAG Graph          |  * Telemetry (Tokens, Latency)    |  * .cascaderouter.yaml Preview    |
|  * AST Metadata & Schema Specs    |  * Mode: [Live / Recorded / Mock] |  * Unified Code Diff View         |
|                                   |  * Rate Limit & Spend Guardrails  |  * Sandbox Regression: [PASSED]   |
+-----------------------------------+-----------------------------------+-----------------------------------+
```

---

## 📁 Repository Structure

```
CascadeRouter/
├── .github/
│   └── workflows/
│       └── tests.yml                 # CI workflow: Unit tests, typechecks & lint
├── backend/
│   ├── api/                          # FastAPI route handlers (/scan, /benchmark, /optimize)
│   ├── compiler/
│   │   ├── ast_scanner.py            # Static AST parser and LLM call discoverer
│   │   ├── dag_builder.py            # Workflow DAG reconstruction
│   │   ├── shadow_runner.py          # Bounded concurrent benchmark runner
│   │   ├── metrics.py                # FinOps cost & latency calculations
│   │   ├── evaluator.py              # Deterministic schema & task validation
│   │   ├── router_optimizer.py       # Lowest-cost model selection engine
│   │   ├── policy_generator.py       # .cascaderouter.yaml generator
│   │   ├── patch_generator.py        # Unified diff & code patch synthesizer
│   │   └── regression_runner.py      # Isolated sandbox regression tester
│   ├── runtime/
│   │   └── cascade_router.py         # Zero-overhead runtime fallback wrapper
│   ├── services/
│   │   ├── nebius_client.py          # Nebius Token Factory async client
│   │   └── tavily_client.py          # Optional Tavily research grounding
│   ├── config.py                     # Central configuration & verified model rates
│   ├── main.py                       # FastAPI application entrypoint
│   └── schemas.py                    # Shared Pydantic data contract models
├── frontend/
│   ├── src/
│   │   ├── components/               # Workbench panes, matrix, diff viewer, DAG
│   │   ├── hooks/                    # API query hooks & WebSocket listeners
│   │   ├── pages/                    # Workbench layout pages
│   │   ├── services/                 # Backend API client
│   │   ├── styles/                   # Tailwind & styling tokens
│   │   ├── types.ts                  # Mirrored TypeScript contracts
│   │   └── App.tsx                   # Main workbench application
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── tests/
│   ├── compiler/                     # Unit tests for scanner, metrics, evaluator
│   ├── fixtures/
│   │   └── sample_repo/              # Bundled sample AI app with over-provisioned calls
│   └── integration/                  # End-to-end integration test suite
├── docs/
│   ├── architecture.md               # Technical specification & system blueprint
│   ├── demo-scenarios.md             # 3-minute hackathon demo script & walkthrough
│   └── test-report.md                # Verification logs and regression test report
├── .env.example                      # Template for API keys & config
├── .gitignore                        # Git exclusion rules
├── LICENSE                           # MIT Open Source License
└── README.md                         # This file
```

---

## 👥 Team Work Breakdown & Ownership

This project is built for the **Nebius × NVIDIA Global AI Hackathon 2026** under strict module ownership:

| Member | Role | Core Deliverable & Owned Files |
| :--- | :--- | :--- |
| **Saba** | **Frontend Lead** | Three-pane workbench UI connected to live API (`frontend/`) |
| **Meenal Sinha** | **Backend Lead & Integration Owner** | FastAPI service, shared schemas, benchmark runner, optimizer, policy & patch generator, runtime wrapper (`backend/`) |
| **Pritam Singh** | **AST Scanner & Agent Graph Lead** | AST static scanner, DAG builder, bundled sample repo & test fixtures (`backend/compiler/ast_scanner.py`, `dag_builder.py`, `tests/fixtures/`) |
| **Aditya** | **Testing, Metrics & Docs Lead** | Cost metrics, evaluator checks, regression runner, integration suite, docs & repo files (`metrics.py`, `evaluator.py`, `regression_runner.py`, `tests/`, `README.md`) |
| **Salman Khurshid**| **Spare Member & Overflow Backup** | PR review, overflow backup for runner/runtime, friction logging |

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python 3.11+
- Node.js 20+ & npm / pnpm
- A Nebius Token Factory API Key ([Nebius AI Studio](https://studio.nebius.ai/))

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/SabaSaiid/CascadeRouter.git
cd CascadeRouter

# Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and insert your NEBIUS_API_KEY
```

Start the FastAPI development server:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
Verify the health check at `http://localhost:8000/api/health`.

### 2. Frontend Setup

```bash
cd frontend

# Install Node dependencies
npm install

# Start the Vite development server
npm run dev
```
Open `http://localhost:5173` in your browser to access the CascadeRouter Workbench IDE.

### 3. Running an Optimization Cycle

1. **Scan**: Click **"Analyze Repository"** or point the IDE to `tests/fixtures/sample_repo`. The AST scanner identifies LLM nodes without executing any code.
2. **Benchmark**: Click **"Run Nemotron Benchmark Matrix"**. CascadeRouter benchmarks prompts across Nano, Lightning, Super-VL, and Ultra tiers on Nebius Token Factory.
3. **Review**: Inspect the FinOps matrix for latency, TTFT, token counts, and cost reduction.
4. **Compile & Patch**: Click **"Generate Patch & Policy"**. Review the unified Git diff and the generated `.cascaderouter.yaml`.
5. **Verify**: Click **"Run Regression Suite"** to verify that tests in the patched sample repository pass cleanly with zero semantic regression.

---

## 🔒 Safety & Operational Guardrails

- **Zero Untrusted Execution**: Scans are purely AST-based (`ast.parse`). Target code is never imported, executed, or `eval`'d during scanning.
- **Hermetic Sandbox**: Code patches are tested inside isolated temporary directories (`tempfile.mkdtemp`) with strict 30-second timeouts and clean environments without host credentials.
- **Judge-Safe Hosted Demo**: The public demo deployment features strict in-memory rate limiting (60 req/min) and daily spend caps to remain free, secure, and accessible throughout the entire judging period (until Dec 15).
- **Badge Transparency**: The UI prominently badges telemetry as **LIVE** (real Nebius API calls), **RECORDED** (deterministic replay), or **MOCK** (offline fixtures).

---

## 🧪 Testing

Run all unit, compiler, and regression tests:
```bash
# Activate virtual environment
source venv/bin/activate

# Run pytest
pytest tests/ -v
```

---

## 📜 Hackathon Compliance & Submission

- **Track**: Track 1 — Coding & Agentic Engineering
- **Models Used**: NVIDIA Nemotron-3-Nano, Nemotron-3.5-Lightning, Nemotron-3.5-Super-VL, Nemotron-3-Ultra-550b
- **Infrastructure**: Nebius Token Factory (Nebius AI Studio API)
- **License**: MIT Open Source License (detectable in repository root)
- **Hosted Demo**: Free and unrestricted for hackathon judges with rate limiting and spend guardrails
- **Demo Video**: [3-Minute YouTube Video Walkthrough Placeholder]

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
