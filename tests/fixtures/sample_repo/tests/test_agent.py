"""Offline regression tests for the triage agent (no network: uses a recording client)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent import workflow


class RecordingClient:
    """Test double for the OpenAI client: returns queued replies, records requests."""

    def __init__(self, *replies: str):
        self._replies = list(replies)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        content = self._replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_classify_intent():
    client = RecordingClient('{"category": "billing", "confidence": 0.93, "urgency": "high"}')
    result = workflow.classify_customer_intent(client, "I was charged twice this month")
    assert result == {"category": "billing", "confidence": 0.93, "urgency": "high"}
    sent = client.requests[0]["messages"]
    assert sent[0]["content"] == workflow.SYSTEM_INTENT_CLASSIFICATION_PROMPT
    assert sent[1]["content"] == "I was charged twice this month"


def test_classify_intent_unknown_category_falls_back_to_general():
    client = RecordingClient('```json\n{"category": "sales", "confidence": 0.4}\n```')
    assert workflow.classify_customer_intent(client, "hi")["category"] == "general"


def test_entity_extraction():
    client = RecordingClient('Here: {"account_id": 48213, "os_version": "Windows 11"}')
    result = workflow.extract_ticket_metadata(client, "Account 48213 on Windows 11")
    assert result == {"account_id": "48213", "os_version": "Windows 11", "error_code": ""}
    assert client.requests[0]["response_format"] == {"type": "json_object"}


def test_entity_extraction_rejects_non_json():
    with pytest.raises(ValueError):
        workflow.extract_ticket_metadata(RecordingClient("no idea"), "ticket")


def test_synthesize_resolution():
    client = RecordingClient("  1. Restart the app.\n2. Clear the cache.  ")
    out = workflow.generate_support_resolution(
        client, "App crashes", {"category": "tech_support"}, {"account_id": "1"}
    )
    assert out == "1. Restart the app.\n2. Clear the cache."
    messages = client.requests[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "Generate fix"}
    assert "Category: tech_support" in messages[1]["content"]


def test_handle_ticket_end_to_end():
    client = RecordingClient(
        '{"category": "tech_support", "confidence": 0.9}',
        '{"account_id": "A-1", "os_version": "macOS 15", "error_code": "E42"}',
        "1. Update to the latest version.",
    )
    out = workflow.handle_ticket(client, "Error E42 on macOS 15, account A-1")
    assert out["intent"]["category"] == "tech_support"
    assert out["metadata"]["error_code"] == "E42"
    assert out["resolution"] == "1. Update to the latest version."
    assert len(client.requests) == 3
    assert json.loads(client.requests[2]["messages"][1]["content"].split("Metadata: ")[1])["account_id"] == "A-1"
