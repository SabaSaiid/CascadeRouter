# Continuous FinOps CI/CD Integration & Budget Gating

## 1. Preventing Silent LLM Cost Regressions

In agile engineering teams, developers frequently alter model parameters or add new agent call sites without understanding the downstream financial implications. Upgrading a simple classification prompt from `Meta-Llama-3.1-8B-Instruct` to an unconstrained frontier model can quietly increase operating expenses by 1,000% to 3,000%.

CascadeRouter integrates into continuous integration (CI) pipelines to provide automated **FinOps Budget Gating**:

```
  Git Push / Pull Request Opened
                │
                ▼
  ┌───────────────────────────────┐
  │  CascadeRouter CI Action      │
  │  1. Run AST Static Scanner    │
  │  2. Compute DAG Cost Delta    │
  │  3. Evaluate Budget Ceiling   │
  └─────────────┬─────────────────┘
                │
        Cost Delta <= Budget Threshold?
        ├──► YES: Pass CI & Post FinOps Summary PR Comment
        └──► NO:  Fail CI & Recommend Pareto-Optimized Model Patch
```

---

## 2. GitHub Actions Workflow Configuration

Below is the standard workflow definition `.github/workflows/finops-gate.yml`:

```yaml
name: CascadeRouter FinOps Gate

on:
  pull_request:
    branches: [ main, staging ]
    paths:
      - '**.py'
      - 'backend/**'

jobs:
  finops_evaluation:
    name: LLM Cost & Latency Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install CascadeRouter CLI
        run: |
          pip install -r requirements.txt

      - name: Run Static FinOps Scan
        id: finops_scan
        run: |
          python -m backend.main --mode scan --fail-on-regression --cost-ceiling 0.50
        env:
          NEBIUS_API_KEY: ${{ secrets.NEBIUS_API_KEY }}
          NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}

      - name: Post FinOps PR Summary
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (fs.existsSync('finops_report.json')) {
              const report = JSON.parse(fs.readFileSync('finops_report.json', 'utf8'));
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: `### 🚀 CascadeRouter FinOps Analysis\n- **Projected Spend Delta:** ${report.cost_delta_percent}%\n- **P95 Latency Impact:** ${report.latency_impact_ms}ms\n- **Recommended Route:** \`${report.recommended_route}\``
              });
            }
```

---

## 3. Pull Request Cost Feedback Loop

When a pull request introduces an inefficient model selection, CascadeRouter automatically posts a detailed diff and recommendation:

> ### ⚠️ CascadeRouter FinOps Alert
> **Cost Regression Detected in `backend/agents/intent_classifier.py:34`**
> - **Current Selection:** `gpt-4o` ($5.00 / 1M tokens)
> - **Recommended Selection:** `Meta-Llama-3.1-8B-Instruct` on Nebius Token Factory ($0.03 / 1M tokens)
> - **Projected Monthly Savings:** **$1,240.00 / month** (99.4% reduction)
> - **Schema Accuracy Difference:** 0.0% (both pass 100% on intent categorization)
> 
> *To automatically apply this optimization, reply `/apply-finops-patch` or trigger the workbench.*

---

## 4. Policy Customization

Teams can define company-wide FinOps policies in `.cascaderouter.yaml`:
- `max_cost_per_call`: Enforces a hard monetary limit on individual call sites.
- `prohibited_models`: Disallows expensive legacy models in production branches.
- `enforce_nemotron_for_json`: Automatically flags any non-Nemotron model when `response_format={"type": "json_object"}` is detected in the AST.
