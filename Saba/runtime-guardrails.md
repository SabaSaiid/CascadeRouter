# Runtime Guardrails & Fault Tolerance

While static compile-time routing optimizes model assignments, dynamic runtime conditions (rate limits, network jitter, unexpected prompt length spikes) necessitate runtime guardrails.

This document describes CascadeRouter's runtime defensive design.

## Core Guardrail Principles

1. **Graceful Cascade Fallback**: If an optimized 8B model call encounters a syntax parse error or timeout, the request cascades automatically to a resilient 70B model.
2. **Circuit Breaking**: Persistent upstream HTTP 429 (rate limit) or 503 (service unavailable) responses temporarily pause routing to affected endpoints, falling back to alternative providers.
3. **Telemetry & Budget Gating**: Enforces daily/monthly expenditure ceilings per application service.

## Fallback Execution Pipeline

```
          [ Incoming Agent Prompt ]
                      |
                      v
      [ Tier 1: Optimized Model (8B) ]
                      |
           +----------+----------+
           |                     |
     (Success 200 OK)      (Schema Parse Error / Timeout)
           |                     |
           v                     v
    [ Pass Downstream ]   [ Tier 2: Cascade Fallback (Nemotron-70B) ]
                                 |
                                 v
                        [ Pass Downstream & Log Incident ]
```

## Implementation Reference

The lightweight runtime client wrapper intercepts requests transparently:

```python
from typing import Any, Dict
import logging
import httpx

logger = logging.getLogger("cascaderouter.guardrails")

class ResilientRouterClient:
    def __init__(self, primary_model: str, fallback_model: str, timeout: float = 5.0):
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout

    async def execute_completion(self, client: httpx.AsyncClient, messages: list, **kwargs) -> Dict[str, Any]:
        try:
            # Attempt primary optimized model
            response = await client.post(
                "https://api.studio.nebius.ai/v1/chat/completions",
                json={"model": self.primary_model, "messages": messages, **kwargs},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning(
                f"Primary model {self.primary_model} failed ({exc}). Cascading to fallback {self.fallback_model}."
            )
            # Invoke fallback tier
            fallback_response = await client.post(
                "https://api.studio.nebius.ai/v1/chat/completions",
                json={"model": self.fallback_model, "messages": messages, **kwargs},
                timeout=self.timeout * 2
            )
            fallback_response.raise_for_status()
            return fallback_response.json()
```

## Telemetry and Cost Ledger

The runtime wrapper emits structured telemetry events for FinOps accounting:

```json
{
  "timestamp": "2026-11-07T16:11:00Z",
  "call_site_id": "triage_intent_01",
  "routed_model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
  "execution_tier": "primary",
  "prompt_tokens": 312,
  "completion_tokens": 28,
  "cost_usd": 0.00001188,
  "latency_ms": 84.2,
  "schema_valid": true
}
```
