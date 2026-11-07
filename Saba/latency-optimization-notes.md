# Latency Optimization Notes: TTFT & Throughput Tuning

Latency in multi-agent LLM systems compounds multiplicatively along serial dependency chains. This technical note details strategies utilized by CascadeRouter to minimize end-to-end latency.

## Anatomy of LLM Request Latency

Total round-trip latency for an LLM inference call is formulated as:

$$T_{\text{latency}} = T_{\text{network\_rtt}} + T_{\text{queue}} + T_{\text{prefill}}(\text{Prompt\_Tokens}) + \sum_{i=1}^{N_{\text{decode}}} T_{\text{decode\_step}}(i)$$

Where:
- $T_{\text{network\_rtt}}$: Network round-trip between application server and Nebius data center.
- $T_{\text{queue}}$: Request scheduling latency in the inference cluster queue.
- $T_{\text{prefill}}$: GPU compute time processing input tokens and computing KV caches ($O(N)$ with FlashAttention / TensorRT-LLM).
- $T_{\text{decode\_step}}$: Memory bandwidth bound generation phase per token.

## Optimization Strategies

### 1. Static Prefix Alignment (KV Cache Reuse)

Nebius Token Factory features prefix caching across consecutive inference requests. When prompt prefixes (such as system guidelines or few-shot exemplars) are byte-identical and located at the start of the prompt:

- Prefill time for cached tokens drops to near zero ($T_{\text{prefill}} \to 0$ for cached prefix).
- TTFT improves by **60% - 85%**.

**CascadeRouter Recommendation**:
Place variable inputs (user query, timestamps, dynamic context) strictly at the end of the prompt payload rather than interleaving them inside the static instruction block.

### 2. Directed Acyclic Graph Fan-Out Parallelization

In monolithic pipelines, developers frequently invoke independent steps sequentially:

```python
# Sequential Bottleneck (Unoptimized)
user_sentiment = await classify_sentiment(ticket)     # 120ms
topic_category = await detect_category(ticket)        # 110ms
fraud_check    = await inspect_fraud_risk(ticket)      # 140ms
# Total Latency = 370ms
```

CascadeRouter's DAG builder flags independent nodes with disjoint dependencies, advising `asyncio.gather` parallelization:

```python
# Parallelized Execution (CascadeRouter Recommendation)
user_sentiment, topic_category, fraud_check = await asyncio.gather(
    classify_sentiment(ticket),
    detect_category(ticket),
    inspect_fraud_risk(ticket)
)
# Total Latency = max(120ms, 110ms, 140ms) = 140ms (62% faster)
```

### 3. Output Token Truncation with `max_tokens` Guard

Prompt developers often omit `max_tokens` or set excessive defaults (`max_tokens=4096`) on simple classification steps. If an 8B or 70B model exhibits unexpected verbosity or loop repetition, request duration explodes.

CascadeRouter statically inspects AST call sites and advises calibrated `max_tokens` ceilings:
- Intent/triage: `max_tokens=64`
- Structured JSON plans: `max_tokens=512`
- Final response drafting: `max_tokens=1024`
