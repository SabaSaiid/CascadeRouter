# Telemetry & Metrics Specification

## 1. Observability Architecture

CascadeRouter incorporates a dual-tier observability framework:
1. **Compilation-Time Metrics**: Measures AST traversal speed, DAG synthesis complexity, Pareto optimization solving duration, and patch validation latencies.
2. **Runtime Telemetry**: Captures granular per-call empirical telemetry across Nebius Token Factory and NVIDIA endpoints, covering Time-To-First-Token (TTFT), tokens per second (TPS), prefill latency, and FinOps unit economics.

```
  ┌─────────────────────────┐
  │   CascadeRouter Runtime │
  └────────────┬────────────┘
               │ OpenTelemetry Traces & Metrics
               ▼
  ┌─────────────────────────┐
  │  OpenTelemetry Collector│
  └───────┬─────────┬───────┘
          │         │
          ▼         ▼
    Prometheus   Jaeger / Tempo
          │
          ▼
   Grafana Dashboards & Alertmanager
```

---

## 2. Standard Metric Definitions

All metrics adhere to OpenTelemetry semantic conventions for generative AI systems, prefixed with `cascaderouter.*`.

### Core FinOps & Performance Metrics

| Metric Name | Type | Unit | Description |
|---|---|---|---|
| `cascaderouter.routing.ttft_seconds` | Histogram | seconds | Time elapsed from HTTP request dispatch until arrival of the first token chunk. |
| `cascaderouter.routing.generation_duration_seconds` | Histogram | seconds | Total wall-clock time spent decoding output tokens. |
| `cascaderouter.tokens.prompt_count` | Counter | tokens | Cumulative count of prompt tokens processed per model. |
| `cascaderouter.tokens.completion_count` | Counter | tokens | Cumulative count of completion tokens generated. |
| `cascaderouter.cost.estimated_usd` | Counter | USD | Cumulative estimated cost based on active pricing matrix. |
| `cascaderouter.cost.savings_usd` | Counter | USD | Realized monetary savings relative to baseline frontier models (e.g., GPT-4o). |
| `cascaderouter.schema.conformity_ratio` | Gauge | ratio (0-1) | Ratio of outputs strictly passing Pydantic/JSON schema validation. |
| `cascaderouter.compiler.ast_scan_seconds` | Histogram | seconds | Time consumed parsing repository AST trees. |

### Histogram Bucketing Strategy for TTFT
Because sub-100ms TTFT is a critical benchmark for interactive multi-agent routing (especially on Nebius Llama-3.1-8B), the histogram boundaries are tuned specifically:

```yaml
cascaderouter.routing.ttft_seconds:
  buckets: [0.025, 0.050, 0.075, 0.100, 0.150, 0.200, 0.300, 0.500, 1.000, 2.500]
```

---

## 3. Metric Dimensions & Labels

Every metric emission carries standardized labels to facilitate deep slicing and dicing in Grafana:

- `model_id`: Canonical identifier (e.g., `Meta-Llama-3.1-8B-Instruct`, `nvidia/Llama-3.1-Nemotron-70B-Instruct`).
- `provider`: Hosting provider (`nebius`, `nvidia`, `openai_baseline`).
- `workload_tier`: Intent category (`triage`, `classification`, `code_generation`, `complex_reasoning`).
- `call_site`: Normalized file and function path identifying the invocation site in the source code.
- `cache_hit`: Boolean indicating if prompt prefix caching was leveraged.

---

## 4. Prometheus Alerting Rules

```yaml
groups:
  - name: cascaderouter_operational_alerts
    rules:
      - alert: TTFTDegradation
        expr: histogram_quantile(0.95, sum(rate(cascaderouter_routing_ttft_seconds_bucket[5m])) by (le, model_id)) > 0.500
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "P95 TTFT exceeds 500ms for {{ $labels.model_id }}"
          description: "Model TTFT is degrading above interactive SLA threshold."

      - alert: SchemaValidationDrop
        expr: cascaderouter_schema_conformity_ratio < 0.95
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Schema conformity dropped below 95% for {{ $labels.model_id }}"
          description: "Structured output parsing is failing; fallback to Nemotron-70B recommended."

      - alert: FinOpsCostSpike
        expr: rate(cascaderouter_cost_estimated_usd[15m]) > 10.0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "FinOps spend rate exceeds $10/15m"
          description: "High token volume or suboptimal model assignment detected."
```

---

## 5. Grafana Dashboard Panels

1. **FinOps Cost Realization**: Real-time stacked area chart depicting baseline vs. optimized spend over time.
2. **TTFT vs. Throughput Scatter**: Comparative scatter plot showing empirical performance clusters across Nebius and NVIDIA instances.
3. **DAG Latency Critical Path**: Heatmap highlighting latency bottlenecks across sequential agent dependencies.
4. **Structured Output Error Rate**: Gauge tracking JSON schema compliance across models.
