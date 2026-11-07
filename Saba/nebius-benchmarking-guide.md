# Nebius Token Factory Benchmarking Guide

Nebius Token Factory provides high-throughput, low-latency LLM inference powered by NVIDIA H100 GPUs. CascadeRouter integrates directly with Nebius endpoints to derive empirical performance profiles for optimization decisions.

## Nebius API Configuration

CascadeRouter accesses Nebius Token Factory using an OpenAI-compatible interface:

- **Base URL**: `https://api.studio.nebius.ai/v1`
- **Authentication**: Bearer token via `NEBIUS_API_KEY`
- **Protocol**: HTTP/2 with Server-Sent Events (SSE) for streaming benchmarks

### Key Models Supported

| Model ID | Provider | Architecture | Cost per 1M Input | Cost per 1M Output |
|---|---|---|---|---|
| `meta-llama/Meta-Llama-3.1-8B-Instruct` | Meta | 8B Parameters | $0.03 | $0.09 |
| `meta-llama/Meta-Llama-3.1-70B-Instruct` | Meta | 70B Parameters | $0.35 | $0.40 |
| `nvidia/Llama-3.1-Nemotron-70B-Instruct` | NVIDIA | 70B Alignment-Tuned | $0.35 | $0.40 |

## Benchmark Metrics Captured

During each benchmark iteration, CascadeRouter records four core performance metrics:

### 1. Time To First Token (TTFT)
Measures the duration from the instant the HTTP request payload is sent until the first chunk containing generated text is received:
$$\text{TTFT} = t_{\text{first\_chunk}} - t_{\text{request\_sent}}$$

TTFT is heavily influenced by:
- GPU prefill speed (KV-cache initialization on NVIDIA H100 SXM5).
- Network round-trip latency to Nebius data centers.
- Prompt token length.

### 2. Decode Token Throughput
Measures the rate of generation after the initial token has arrived:
$$\text{Throughput} = \frac{N_{\text{completion\_tokens}} - 1}{t_{\text{stream\_end}} - t_{\text{first\_chunk}}}$$
Expressed in **tokens per second (tokens/s)**.

### 3. Total Request Latency
The complete round-trip wall-clock duration from dispatch to stream close:
$$\text{Latency}_{\text{total}} = t_{\text{stream\_end}} - t_{\text{request\_sent}}$$

### 4. Schema Compliance Rate
For tasks requiring structured JSON outputs, the generated string is parsed against the expected JSON Schema or Pydantic validation model. A binary pass/fail indicator determines routing eligibility.

## Live Benchmarking Workflow

```python
# Simplified snippet of LiveBenchmarkExecutor
import time
import httpx

async def benchmark_nebius_model(model_name: str, prompt: str, api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.1,
    }
    
    t_start = time.perf_counter()
    first_token_time = None
    tokens_received = 0
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.studio.nebius.ai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0
        ) as response:
            async for chunk in response.aiter_lines():
                if chunk.startswith("data: ") and chunk != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    tokens_received += 1
                    
    t_end = time.perf_counter()
    ttft_ms = (first_token_time - t_start) * 1000
    total_ms = (t_end - t_start) * 1000
    decode_tps = tokens_received / (t_end - first_token_time) if first_token_time else 0
    
    return {
        "model": model_name,
        "ttft_ms": round(ttft_ms, 2),
        "total_ms": round(total_ms, 2),
        "tokens_per_sec": round(decode_tps, 2),
        "token_count": tokens_received
    }
```

## Offline Emulation Fallback

For environments without live API credentials or running in air-gapped CI/CD pipelines, CascadeRouter includes a calibrated emulation fallback. The fallback uses empirical distribution curves obtained from thousands of Nebius H100 test runs, preserving realistic variance, jitter, and throughput distributions for development and testing.
