# FinOps Cost Attribution, Multi-Tenant Chargeback & Budget Enforcers

## 1. Unit Economics in Shared LLM Infrastructure

When multiple departments, microservices, or external tenants share a centralized LLM routing infrastructure, assigning financial responsibility without accurate per-call accounting leads to unallocated overhead and uncontrolled cloud expenditure.

CascadeRouter introduces a granular **Cost Attribution & Chargeback Engine**:

```
  Incoming LLM Request (with Metadata Headers)
  Headers: X-Department: Engineering, X-Project: Search-V2
                 │
                 ▼
  ┌────────────────────────────────────────────────────────┐
  │              Token Metering & Attribution              │
  │     (Calculates Prompt & Completion Token Costs)       │
  └────────────────────────┬───────────────────────────────┘
                           │
                           ▼
  ┌────────────────────────────────────────────────────────┐
  │              Tenant Quota Enforcer (Redis)             │
  │     (Verifies against allocated departmental budget)   │
  └────────────────────────┬───────────────────────────────┘
                           │
                Budget Threshold Check
                ├──► Under Quota: Forward to Nebius / NVIDIA
                └──► Exceeded: Soft-Throttle / Reroute to 8B Budget Tier
```

---

## 2. Cost Attribution Formulation

For any invocation $k$ executed under tenant $T$ on model $M$:

$$\text{Cost}(k) = \left( \frac{\text{Tokens}_{\text{prompt}}}{10^6} \times P_{\text{in}}(M) \right) + \left( \frac{\text{Tokens}_{\text{completion}}}{10^6} \times P_{\text{out}}(M) \right)$$

Where active pricing rates ($P_{\text{in}}, P_{\text{out}}$) are dynamically pulled from the pricing configuration:

| Provider | Model ID | Input Price / 1M | Output Price / 1M |
|---|---|---|---|
| **Nebius Token Factory** | `Meta-Llama-3.1-8B-Instruct` | $0.030 | $0.060 |
| **Nebius Token Factory** | `Meta-Llama-3.1-70B-Instruct` | $0.350 | $0.400 |
| **NVIDIA NIM** | `nvidia/Llama-3.1-Nemotron-70B-Instruct` | $0.350 | $0.400 |
| *Baseline Reference* | `gpt-4o` | *$2.500* | *$10.000* |

---

## 3. Departmental Quota Policies & Graceful Throttling

CascadeRouter supports three budget enforcement tiers:

1. **Soft Quota (80% Budget Consumed)**:
   - Emits an asynchronous notification to Slack/PagerDuty.
   - Recommends down-tiering non-critical background jobs to 8B models.
2. **Hard Ceiling (100% Budget Consumed)**:
   - Restricts further invocations of frontier models for that tenant.
   - Automatically down-routes subsequent requests to `Meta-Llama-3.1-8B-Instruct` on Nebius Token Factory, maintaining operational continuity while arresting cost growth.
3. **Emergency Circuit Break**:
   - Rejects non-essential requests with HTTP 429 (`BudgetExceededQuota`).

---

## 4. Chargeback Export & ERP Integration

Telemetry aggregates are serialized periodically into standard accounting schemas:
- CSV / Parquet exports partitioned by `year=YYYY/month=MM/tenant=XYZ/`
- Direct compatibility with AWS Cost Explorer, GCP Cloud Billing, and Snowflake data warehouses.
