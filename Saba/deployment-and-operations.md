# Production Deployment & Operations Guide

This guide details operational practices for deploying CascadeRouter within engineering teams, CI/CD automation pipelines, and production environments.

## Deployment Topologies

CascadeRouter supports three operational modes:

1. **Interactive Workbench (Local Developer)**: Full-featured web interface running locally on `localhost:3000` with FastAPI backend on `localhost:8000`.
2. **Headless CLI Compiler**: Automated scanner and patch generator for shell scripts and automated developer workflows.
3. **CI/CD FinOps Quality Gate**: Continuous GitHub Actions / GitLab CI step verifying that incoming PRs do not introduce unoptimized frontier model hardcoding.

---

## 1. Local Workbench Setup

The bundled `start.sh` script automates dependency management and environment setup:

```bash
# Clone the repository
git clone https://github.com/SabaSaiid/CascadeRouter.git
cd CascadeRouter

# Configure API Key (optional for live benchmarks, offline emulation active by default)
export NEBIUS_API_KEY="your-nebius-api-key"

# Launch the full stack (backend + frontend)
./start.sh
```

### Port Allocations
- **Web UI**: `http://localhost:3000` (Vite + React 19)
- **FinOps API**: `http://localhost:8000` (FastAPI + Uvicorn)
- **API Documentation**: `http://localhost:8000/docs` (Swagger UI)

---

## 2. CI/CD FinOps Gating (GitHub Actions)

To prevent developers from accidentally committing costly frontier models (e.g. hardcoding `gpt-4o` for basic classification steps), add CascadeRouter as a PR gate:

```yaml
name: FinOps Static Audit

on:
  pull_request:
    branches: [ main ]

jobs:
  finops-lint:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install CascadeRouter Scanner
        run: |
          pip install -r requirements.txt

      - name: Run Zero-Execution AST Audit
        run: |
          python -m backend.scanner.ast_scanner --audit-dir ./src --max-allowed-frontier-nodes 1
```

If an unapproved monolithic model call is detected where an 8B model or Nemotron-70B is applicable, the CI pipeline fails with an actionable patch diff suggestion.

---

## 3. Environment Variables Reference

| Variable | Type | Default | Description |
|---|---|---|---|
| `NEBIUS_API_KEY` | string | `""` | Bearer token for Nebius Token Factory live endpoints |
| `NEBIUS_BASE_URL` | string | `https://api.studio.nebius.ai/v1` | Base API URL |
| `ROUTER_PORT` | integer | `8000` | FastAPI server listening port |
| `ENABLE_AUTO_BACKUP` | boolean | `true` | Automatically write `.bak` files before applying patches |
| `EMULATION_MODE` | boolean | `false` | Force offline empirical distribution emulation |
