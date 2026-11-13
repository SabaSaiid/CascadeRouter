# Multi-Objective Pareto Frontier Algorithms & Solvers

## 1. Problem Formulation

Selecting the optimal LLM configuration for a multi-agent system requires balancing three competing objectives across each DAG node $i \in \{1, \dots, N\}$:
1. **Cost Minimization ($C$)**: Total financial cost per 1M tokens across prompt and completion phases.
2. **Latency Minimization ($L$)**: End-to-end critical path latency (TTFT + token generation duration).
3. **Quality / Schema Conformity ($Q$)**: Pass rate on structured schema validation and semantic benchmarks.

```
       Cost ($)
          ▲
          │      ● (Baseline: GPT-4o)
          │
          │             ● (Suboptimal Route)
          │
          │       ★ (Pareto Frontier: Nemotron-70B)
          │
          │   ★ (Pareto Frontier: Llama-3.1-8B)
          └────────────────────────────────────────► Latency (ms)
```

A routing candidate $\mathbf{x} = (x_1, \dots, x_N)$ strictly dominates another candidate $\mathbf{y}$ if:
$$\forall j \in \{C, L\}, \quad f_j(\mathbf{x}) \le f_j(\mathbf{y}) \quad \land \quad f_Q(\mathbf{x}) \ge f_Q(\mathbf{y})$$
with at least one strict inequality.

---

## 2. The $\epsilon$-Constraint Scalarization Method

Because weighted-sum scalarization fails to explore concave regions of the Pareto frontier, CascadeRouter's `router_optimizer.py` implements the **$\epsilon$-Constraint Method**:

$$\min_{\mathbf{x}} \quad \sum_{i=1}^{N} C_i(x_i)$$
$$\text{subject to:}$$
$$\sum_{i \in \text{CriticalPath}} L_i(x_i) \le \epsilon_{\text{latency}}$$
$$Q_i(x_i) \ge \epsilon_{\text{quality}}, \quad \forall i \in \{1, \dots, N\}$$
$$x_{i,m} \in \{0, 1\}, \quad \sum_{m \in M} x_{i,m} = 1$$

Where:
- $x_{i,m} = 1$ if node $i$ is assigned model $m$.
- $\epsilon_{\text{latency}}$ is the SLA threshold on critical path DAG latency.
- $\epsilon_{\text{quality}}$ is the minimum acceptable schema validation rate (e.g., $98.0\%$).

---

## 3. Algorithmic Workflow in `router_optimizer.py`

```python
def compute_pareto_frontier(
    nodes: list[DAGNode],
    benchmarks: dict[str, ModelMetrics],
    latency_sla_ms: float,
    min_quality_score: float
) -> list[RoutingSolution]:
    """
    Solves the integer program across discretized epsilon steps
    to construct the full non-dominated frontier.
    """
    pareto_solutions = []
    # Discretize latency SLA into 20 equidistant evaluation steps
    epsilon_steps = np.linspace(min_feasible_latency, latency_sla_ms, num=20)
    
    for eps in epsilon_steps:
        solution = solve_ilp(
            nodes=nodes,
            benchmarks=benchmarks,
            max_latency=eps,
            min_quality=min_quality_score
        )
        if solution.is_feasible and not is_dominated(solution, pareto_solutions):
            pareto_solutions.append(solution)
            
    return prune_dominated_solutions(pareto_solutions)
```

---

## 4. Empirical Optimization Results

Benchmarking a 4-node Multi-Agent Customer Ingestion Pipeline yields three primary operating regimes on the Pareto frontier:

| Mode | Assigned Routing | Total Cost / 1k Invocations | Critical Path Latency | Schema Accuracy |
|---|---|---|---|---|
| **Ultra-FinOps (Budget)** | 8B across all nodes | **$0.12** (89% savings) | 380 ms | 94.2% |
| **Balanced (Recommended)** | 8B (Triage) $\to$ Nemotron-70B (Extraction) $\to$ 8B (Summary) | **$0.38** (66% savings) | 620 ms | **99.6%** |
| **Maximum Accuracy** | Nemotron-70B across all nodes | **$0.82** (25% savings) | 1,240 ms | **99.9%** |
| *Baseline (Unoptimized)* | *GPT-4o across all nodes* | *$1.10 (Baseline)* | *1,450 ms* | *99.8%* |

### Conclusion
The Balanced route (combining Nebius-hosted Llama-3.1-8B for preliminary sorting with NVIDIA Nemotron-70B for strict schema-constrained generation) achieves a **66% cost reduction** and **57% latency reduction** while matching or exceeding frontier schema accuracy.
