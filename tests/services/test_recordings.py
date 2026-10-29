import json

import pytest

from backend.services.llm import CompletionResult, LLMError, request_key
from backend.services.recordings import RecordingClient, RecordingStore, RecordingWriter

MSGS = [{"role": "user", "content": "hi"}]
RESULT = CompletionResult("hello", 5, 1, True, 120.0, 30.0)


class Live:
    def __init__(self):
        self.calls = 0

    async def complete(self, model, messages, params):
        self.calls += 1
        return RESULT


async def test_writer_records_and_client_replays(tmp_path):
    store = RecordingStore(tmp_path / "rec")
    live = Live()
    assert await RecordingWriter(live, store).complete("m", MSGS, {"t": 0}) == RESULT
    files = list((tmp_path / "rec").glob("*.json"))
    assert len(files) == 1 and files[0].stem == request_key("m", MSGS, {"t": 0})
    payload = json.loads(files[0].read_text())
    assert payload["model"] == "m" and payload["responses"][0]["result"]["text"] == "hello"
    assert payload["responses"][0]["recorded_at"]
    assert not list((tmp_path / "rec").glob("*.tmp"))

    replay = RecordingClient(store)
    assert await replay.complete("m", MSGS, {"t": 0}) == RESULT
    assert live.calls == 1


async def test_missing_recording_is_an_error_not_fake_data(tmp_path):
    with pytest.raises(LLMError, match="no recording"):
        await RecordingClient(RecordingStore(tmp_path)).complete("m", MSGS, {})


async def test_different_params_do_not_match(tmp_path):
    store = RecordingStore(tmp_path)
    await RecordingWriter(Live(), store).complete("m", MSGS, {"t": 0})
    with pytest.raises(LLMError):
        await RecordingClient(store).complete("m", MSGS, {"t": 1})


def test_corrupt_recording(tmp_path):
    store = RecordingStore(tmp_path)
    key = request_key("m", MSGS, {})
    (tmp_path / f"{key}.json").write_text("{not json")
    with pytest.raises(LLMError, match="corrupt"):
        store.get(key)
    (tmp_path / f"{key}.json").write_text(json.dumps({"result": {"text": "x"}}))
    with pytest.raises(LLMError, match="corrupt"):
        store.get(key)


@pytest.mark.parametrize("key", ["../evil", "abc", "G" * 64, ""])
def test_invalid_keys_rejected(tmp_path, key):
    with pytest.raises(ValueError):
        RecordingStore(tmp_path).get(key)


async def test_failed_live_call_is_not_recorded(tmp_path):
    class Failing:
        async def complete(self, *a):
            raise LLMError("boom")

    store = RecordingStore(tmp_path)
    with pytest.raises(LLMError):
        await RecordingWriter(Failing(), store).complete("m", MSGS, {})
    assert not list(tmp_path.glob("*"))


def test_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    import backend.services.recordings as rec

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(rec.os, "replace", boom)
    store = RecordingStore(tmp_path)
    with pytest.raises(OSError):
        store.put(request_key("m", MSGS, {}), "m", RESULT)
    assert list(tmp_path.iterdir()) == []


async def test_repeated_identical_requests_replay_in_order(tmp_path):
    class Varying:
        def __init__(self):
            self.n = 0

        async def complete(self, model, messages, params):
            self.n += 1
            return CompletionResult(f"answer {self.n}", 5, 1, True, 100.0 * self.n, None)

    store = RecordingStore(tmp_path)
    writer = RecordingWriter(Varying(), store)
    for _ in range(2):
        await writer.complete("m", MSGS, {})
    assert store.count(request_key("m", MSGS, {})) == 2
    replay = RecordingClient(store)
    texts = [(await replay.complete("m", MSGS, {})).text for _ in range(3)]
    assert texts == ["answer 1", "answer 2", "answer 2"]  # extra replays reuse the last real one
    assert (await RecordingClient(store).complete("m", MSGS, {})).text == "answer 1"  # fresh run restarts


def test_single_response_legacy_format_is_read(tmp_path):
    key = request_key("m", MSGS, {})
    (tmp_path / f"{key}.json").write_text(json.dumps({"model": "m", "recorded_at": "t", "result": RESULT.to_dict()}))
    store = RecordingStore(tmp_path)
    assert store.get(key) == RESULT and store.count(key) == 1


def test_put_replaces_corrupt_file(tmp_path):
    key = request_key("m", MSGS, {})
    (tmp_path / f"{key}.json").write_text("{broken")
    store = RecordingStore(tmp_path)
    with pytest.raises(LLMError):
        store.count(key)
    store.put(key, "m", RESULT)
    assert store.get(key) == RESULT


def test_empty_response_list_is_missing(tmp_path):
    key = request_key("m", MSGS, {})
    (tmp_path / f"{key}.json").write_text(json.dumps({"model": "m", "responses": []}))
    assert RecordingStore(tmp_path).get(key) is None
