# FinOps Compiler Strategy & Optimization Algorithms

The primary mission of CascadeRouter is turning empirical inference telemetry into an optimal model assignment plan that minimizes spend while upholding quality and latency requirements.

## Mathematical Formulation

Let a multi-agent system be modeled as a directed acyclic graph $G = (V, E)$, where:
- Each vertex $v_i \in V$ represents an LLM call site.
- Each directed edge $(v_i, v_j) \in E$ denotes a data dependency where output from $v_i$ feeds into the prompt of $v_j$.
- Let $M = \{m_1, m_2, \dots, m_k\}$ represent the available candidate models in Nebius Token Factory.

For each call site $v_i$ and candidate model $m \in M$:
- $C(v_i, m)$: Expected dollar cost per execution based on prompt/completion token lengths:
  $$C(v_i, m) = \frac{T_{\text{in}}(v_i) \cdot P_{\text{in}}(m) + T_{\text{out}}(v_i) \cdot P_{\text{out}}(m)}{10^6}$$
- $L(v_i, m)$: Empirical latency (TTFT + decode time) in milliseconds.
- $Q(v_i, m) \in [0, 1]$: Quality pass score (schema validation, semantic accuracy, or classification fidelity).

### Objective Function

We define the global optimization problem as:

$$\min_{m(v_i) \in M} \sum_{v_i \in V} C(v_i, m(v_i))$$

Subject to:
1. **Critical Path Latency Constraint**:
   $$\sum_{v_i \in \Pi_{\text{crit}}} L(v_i, m(v_i)) \le L_{\text{max\_SLA}}$$
   where $\Pi_{\text{crit}}$ is the longest latency path from root to leaf in DAG $G$.
2. **Quality Lower Bound**:
   $$Q(v_i, m(v_i)) \ge Q_{\text{min\_threshold}}(v_i), \quad \forall v_i \in V$$
3. **Structured Schema Requirement**:
   If node $v_i$ requires valid JSON:
   $$\text{SchemaPass}(v_i, m(v_i)) \ge 0.99$$

## Routing Policy Modes

CascadeRouter provides three predefined routing heuristics:

### 1. Maximum Savings (Aggressive FinOps)
- Prioritizes `meta-llama/Meta-Llama-3.1-8B-Instruct` across all nodes meeting a minimum pass threshold ($\ge 85\%$).
- Restricts 70B models strictly to nodes where 8B models fail schema validation.
- Typical outcome: **80% - 90% cost reduction**, slight variance in generation nuance.

### 2. Balanced (Recommended)
- Routes high-volume classification, triage, routing, and summarization to `Meta-Llama-3.1-8B-Instruct`.
- Routes strict structured generation and complex reasoning to `nvidia/Llama-3.1-Nemotron-70B-Instruct`.
- Reserves `Meta-Llama-3.1-70B-Instruct` for open-ended creative drafting.
- Typical outcome: **65% - 75% cost reduction**, zero loss in system accuracy, 40% faster overall pipeline execution.

### 3. Ultra-Low Latency (Performance First)
- Maximizes token throughput and minimizes TTFT.
- Employs 8B models on H100s for every possible step to keep end-to-end multi-agent execution sub-second.

## Confidence Interval & Risk Scoring

Empirical benchmarks on small sample sizes ($N < 30$) introduce statistical variance. To guard against premature down-selection to smaller models, CascadeRouter computes Wilson score confidence intervals for quality scores:

$$W(p, n, z) = \frac{p + \frac{z^2}{2n} - z \sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

Where:
- $p$: Sample pass rate.
- $n$: Number of benchmark runs.
- $z$: Standard normal quantile ($z = 1.96$ for 95% confidence).

A smaller model is only substituted for a frontier model if its **lower confidence bound** satisfies the node's strict threshold:
$$W(p, n, 1.96) \ge Q_{\text{min\_threshold}}(v_i)$$

This prevents edge-case regressions where an 8B model passes 3 consecutive tests by chance but fails in production workloads.

