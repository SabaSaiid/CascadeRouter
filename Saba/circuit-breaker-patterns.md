# Runtime Circuit Breaker Patterns & Failover Hierarchy

## 1. Resilience in Multi-Provider Environments

Production systems relying on external model endpoints encounter transient rate-limits (HTTP 429), regional outages (HTTP 503), and unpredictable latency spikes. CascadeRouter's runtime layer incorporates a high-performance **Finite State Circuit Breaker** designed to prevent cascading failure across multi-agent pipelines.

```
       [ Normal Operations ]
                 │
                 ▼
       ┌───────────────────┐
       │      CLOSED       │ ◄─────────────────────────┐
       └─────────┬─────────┘                           │
                 │ Consecutive Failures > Threshold    │
                 ▼                                     │ Success Rate > 90%
       ┌───────────────────┐                           │
       │       OPEN        │                           │
       └─────────┬─────────┘                           │
                 │ Sleep Window Expires (Cool-off)     │
                 ▼                                     │
       ┌───────────────────┐                           │
       │     HALF-OPEN     │ ──────────────────────────┘
       └───────────────────┘
```

---

## 2. Circuit Breaker State Dynamics

| State | Routing Behavior | Trigger Condition | Fallback Action |
|---|---|---|---|
| **CLOSED** | Requests flow to primary optimized model (e.g., Nebius Token Factory). | Normal operating state ($E < \theta$). | None. Primary provider handles load. |
| **OPEN** | Primary endpoint immediately bypassed without waiting for network timeout. | Consecutive failures $\ge 5$ or error rate $> 20\%$ in rolling 60s window. | Immediate reroute to designated secondary fallback model. |
| **HALF-OPEN** | Probe subset of traffic (5% of requests) through primary endpoint. | Cool-off duration (30 seconds) has elapsed. | Non-probe traffic continues routing to fallback; probe responses evaluate recovery. |

---

## 3. Fallback Hierarchy Matrix

When a primary model endpoint enters the `OPEN` state, CascadeRouter executes deterministic fallback based on the call site's functional tier:

```
  Tier 1: Intent Triage / Simple Extraction
  Primary:   Nebius Meta-Llama-3.1-8B-Instruct
  Fallback:  Nebius Meta-Llama-3.1-70B-Instruct -> OpenAI gpt-4o-mini

  Tier 2: Strict JSON Schema / Complex Function Calling
  Primary:   NVIDIA Llama-3.1-Nemotron-70B-Instruct (NIM)
  Fallback:  Nebius Meta-Llama-3.1-70B-Instruct -> OpenAI gpt-4o
```

---

## 4. Exponential Backoff with Decorrelated Jitter

To prevent the "thundering herd" problem when upstream endpoints recover, retries apply **Decorrelated Jitter**:

$$t_{\text{sleep}} = \min(t_{\text{max}}, \; \text{Uniform}(t_{\text{base}}, \; t_{\text{previous}} \times 3))$$

This spreads out concurrent retry bursts across a wide distribution, avoiding synchronized re-saturation of GPU inference queues.

---

## 5. Runtime Telemetry & Health Checks

The circuit breaker emits Prometheus metrics on state transitions:

```yaml
# Metrics emitted by runtime/circuit_breaker.py
cascaderouter_circuit_state{provider="nebius", model="Meta-Llama-3.1-8B-Instruct"} 0 # 0=Closed, 1=Half-Open, 2=Open
cascaderouter_circuit_fallback_total{from_model="8b", to_model="70b"} 14
```

These metrics allow SRE teams to identify provider degradation before end-user SLAs are compromised.
