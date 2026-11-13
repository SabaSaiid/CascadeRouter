# Empirical Benchmarking Methodology & Statistical Filtering

## 1. Ground Truth Benchmarking Philosophy

CascadeRouter rejects synthetic parameter guesswork. To make defensible routing decisions, the optimizer measures real performance over live API endpoints (Nebius Token Factory and NVIDIA NIM) under controlled, reproducible conditions.

```
  ┌─────────────────────────────────────────────────────────┐
  │                 Test Asset Ingestion                    │
  │     (Representative prompts, tool schemas, payloads)    │
  └────────────────────────────┬────────────────────────────┘
                               │
                               ▼
  ┌─────────────────────────────────────────────────────────┐
  │              Warm-Up & Connection Pooling               │
  │    (3 discarded warm-up runs to prime TCP & TLS caches) │
  └────────────────────────────┬────────────────────────────┘
                               │
                               ▼
  ┌─────────────────────────────────────────────────────────┐
  │              Streaming Execution Harness                │
  │    (High-precision monotonic clock per token event)     │
  └────────────────────────────┬────────────────────────────┘
                               │
                               ▼
  ┌─────────────────────────────────────────────────────────┐
  │         Statistical Outlier Filtering (IQR / Trim)      │
  │      (P50, P90, P95, Mean, Wilson Score Confidence)     │
  └─────────────────────────────────────────────────────────┘
```

---

## 2. Experimental Protocol

Each benchmark trial in `live_benchmark.py` follows strict statistical guidelines:

1. **Pre-Flight Warm-Up**:
   - 3 initial invocations are conducted and discarded to prime DNS resolution, TLS session handshakes, and server-side KV caches.
2. **Measurement Iterations**:
   - A minimum of $N = 10$ randomized sample trials are executed across distinct prompt lengths:
     - *Short context*: 128 - 512 tokens
     - *Medium context*: 1,024 - 4,096 tokens
     - *Long context*: 8,192 - 16,384 tokens
3. **Monotonic High-Precision Timers**:
   - Timestamps are captured using `time.perf_counter_ns()`.
   - $T_0$: Request dispatched to socket.
   - $T_1$: First byte / SSE chunk received (TTFT).
   - $T_{\text{end}}$: Stream completion (EOS token received).

---

## 3. Outlier Filtering & Statistical Aggregation

Raw network latency over public cloud endpoints is subject to tail variance caused by internet routing and GPU scheduler preemption.

### Interquartile Range (IQR) Trimming
Let $Q_1$ and $Q_3$ represent the 25th and 75th percentiles of measured TTFT. The Interquartile Range is $\text{IQR} = Q_3 - Q_1$.

Any observation $x$ where:
$$x > Q_3 + 1.5 \times \text{IQR} \quad \text{or} \quad x < Q_1 - 1.5 \times \text{IQR}$$
is marked as a transient network anomaly and excluded from the baseline routing average.

### Wilson Score Lower Bound for Quality
Schema accuracy $p$ across $n$ validation trials is reported as the lower bound of the Wilson score interval at 95% confidence level:

$$w^{-} = \frac{p + \frac{z^2}{2n} - z \sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

This ensures that small-sample trials (e.g. $n=10$ with 100% pass) are penalized conservatively relative to large-sample empirical validations ($n=1000$).

---

## 4. Benchmark Asset Representation

The benchmark runner supports both live execution against endpoints and reproducible offline replay via `offline_benchmark.py`. This guarantees deterministic CI/CD evaluations even when external API credentials are not provisioned in developer environments.
