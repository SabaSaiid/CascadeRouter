"""Customer-support triage agent.

Three LLM steps, all hard-wired to the largest Nemotron tier:
classify intent -> extract ticket metadata -> synthesize a resolution.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

ULTRA_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"

SYSTEM_INTENT_CLASSIFICATION_PROMPT = (
    "You are a support triage classifier. Read the customer's message and reply with a "
    "single JSON object with keys: category (one of billing, tech_support, general), "
    "confidence (number between 0 and 1) and urgency (one of low, medium, high). "
    "Reply with JSON only."
)

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["billing", "tech_support", "general"]},
        "confidence": {"type": "number"},
        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["category", "confidence"],
}

ENTITY_EXTRACTION_PROMPT = (
    "Extract metadata from the support ticket. Reply with a JSON object with keys: "
    "account_id (string), os_version (string, empty if unknown) and error_code "
    "(string, empty if unknown). Reply with JSON only."
)

ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "account_id": {"type": "string"},
        "os_version": {"type": "string"},
        "error_code": {"type": "string"},
    },
    "required": ["account_id"],
}

RESOLUTION_SYNTHESIS_TEMPLATE = (
    "You are a senior support engineer. Using the ticket, its category and the extracted "
    "metadata, write a numbered, step-by-step resolution the customer can follow."
)


def make_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
    )


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"model did not return JSON: {content!r}")
    return json.loads(text[start : end + 1])


def classify_customer_intent(client: OpenAI, query: str) -> dict[str, Any]:
    """Classifies customer inquiry into categories: billing, tech_support, or general."""
    response = client.chat.completions.create(
        model="nvidia/Nemotron-3-Ultra-550b-a55b",
        messages=[
            {"role": "system", "content": SYSTEM_INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0,
    )
    result = _parse_json(response.choices[0].message.content)
    if result.get("category") not in ("billing", "tech_support", "general"):
        result["category"] = "general"
    return result


def extract_ticket_metadata(client: OpenAI, ticket: str) -> dict[str, Any]:
    """Extracts account number, software version, and operating system from ticket."""
    prompt = f"{ENTITY_EXTRACTION_PROMPT}\n\nTicket:\n{ticket}"
    res = client.chat.completions.create(
        model=ULTRA_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    data = _parse_json(res.choices[0].message.content)
    return {
        "account_id": str(data.get("account_id", "")),
        "os_version": str(data.get("os_version", "")),
        "error_code": str(data.get("error_code", "")),
    }


def generate_support_resolution(
    client: OpenAI, ticket: str, intent: dict[str, Any], metadata: dict[str, Any]
) -> str:
    """Synthesizes step-by-step resolution based on diagnostics."""
    history = [
        {"role": "system", "content": RESOLUTION_SYNTHESIS_TEMPLATE},
        {
            "role": "user",
            "content": (
                f"Ticket:\n{ticket}\n\nCategory: {intent['category']}\n"
                f"Metadata: {json.dumps(metadata)}"
            ),
        },
    ]
    resolution = client.chat.completions.create(
        model="nvidia/Nemotron-3-Ultra-550b-a55b",
        messages=history + [{"role": "user", "content": "Generate fix"}],
        max_tokens=1024,
    )
    return resolution.choices[0].message.content.strip()


def handle_ticket(client: OpenAI, ticket: str) -> dict[str, Any]:
    """Runs the full triage pipeline for one ticket."""
    intent = classify_customer_intent(client, ticket)
    metadata = extract_ticket_metadata(client, ticket)
    resolution = generate_support_resolution(client, ticket, intent, metadata)
    return {"intent": intent, "metadata": metadata, "resolution": resolution}
