"""Body deadlines and aggregate admission without sockets or pytest plugins."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.api.boundaries import RequestBoundary
from backend.config import BackendConfig


def scope():
    return {"type": "http", "method": "POST", "path": "/api/scan", "headers": [(b"host", b"localhost")]}


def test_body_read_deadline_is_controlled_before_route_execution():
    async def scenario():
        reached = []
        sent = []

        async def inner(*args):
            reached.append(True)

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)

        middleware = RequestBoundary(inner, settings=BackendConfig(scan_timeout_seconds=1))
        await middleware(scope(), receive, send)
        assert not reached and sent[0]["status"] == 503
        assert json.loads(sent[1]["body"])["code"] == "capability_unavailable"

    asyncio.run(scenario())


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def rate_boundary(clock, **limits):
    async def inner(_scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    return RequestBoundary(inner, settings=BackendConfig(**limits), clock=clock)


async def exchange(boundary, *, client=("127.0.0.1", 1234), path="/api/scan", method="POST", headers=(),
                   chunks=(b"",), forbid_read=False):
    request = {**scope(), "client": client, "path": path, "method": method,
               "headers": [(b"host", b"localhost"), *headers]}
    sent, reads = [], []
    messages = [{"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
                for index, chunk in enumerate(chunks)]
    async def receive():
        assert not forbid_read, "A rejected request consumed its body."
        reads.append(True)
        return messages.pop(0)
    async def send(message):
        sent.append(message)
    await boundary(request, receive, send)
    body = b"".join(message.get("body", b"") for message in sent)
    return sent[0]["status"], json.loads(body) if body else None, len(reads)


def test_token_bucket_refills_continuously_and_never_exceeds_its_burst():
    clock = Clock()
    boundary = rate_boundary(clock, request_rate_limit=3, request_rate_window_seconds=60)
    async def scenario():
        assert [(await exchange(boundary))[0] for _ in range(4)] == [204, 204, 204, 429]
        clock.now = 20
        assert (await exchange(boundary))[0] == 204
        assert (await exchange(boundary, forbid_read=True))[0] == 429
        clock.now = 600
        assert [(await exchange(boundary))[0] for _ in range(4)] == [204, 204, 204, 429]
    asyncio.run(scenario())


def test_excess_request_is_sanitized_without_consuming_body_or_reaching_route(caplog):
    boundary = rate_boundary(Clock(), request_rate_limit=1)
    async def scenario():
        assert (await exchange(boundary))[0] == 204
        status, error, reads = await exchange(boundary, forbid_read=True, chunks=(b"PRIVATE_BODY",),
            headers=((b"origin", b"http://localhost:5173"), (b"content-length", b"bad")))
        assert status == 429 and error["code"] == "capacity_exceeded" and reads == 0
        assert error["request_id"].startswith("req_")
        assert "PRIVATE" not in json.dumps(error) + caplog.text
    asyncio.run(scenario())


def test_forwarding_headers_ports_and_paths_cannot_reset_peer_quota():
    boundary = rate_boundary(Clock(), request_rate_limit=1)
    async def scenario():
        assert (await exchange(boundary))[0] == 204
        for index in range(30):
            result = await exchange(boundary, client=("127.0.0.1", 2000 + index), path="/api/runs/" + str(index),
                headers=((b"x-forwarded-for", f"192.0.2.{index}".encode()),
                         (b"x-real-ip", f"198.51.100.{index}".encode()), (b"forwarded", b"for=203.0.113.1")), forbid_read=True)
            assert result[0] == 429
        assert len(boundary.limiter.buckets) == 1
    asyncio.run(scenario())


def test_distinct_peers_have_independent_limits_within_capacity():
    boundary = rate_boundary(Clock(), request_rate_limit=2, request_rate_max_clients=2)
    async def scenario():
        for host in ("127.0.0.1", "127.0.0.2"):
            assert [(await exchange(boundary, client=(host, 1)))[0] for _ in range(3)] == [204, 204, 429]
        assert (await exchange(boundary, client=("127.0.0.3", 1), forbid_read=True))[0] == 429
    asyncio.run(scenario())


def test_identity_churn_is_bounded_and_cannot_evict_a_depleted_bucket():
    boundary = rate_boundary(Clock(), request_rate_limit=1, request_rate_max_clients=3)
    async def scenario():
        for index in range(3):
            assert (await exchange(boundary, client=(f"127.0.0.{index + 1}", 1)))[0] == 204
        for index in range(1024):
            host = f"192.0.{index // 256}.{index % 256}"
            assert (await exchange(boundary, client=(host, 1), forbid_read=True))[0] == 429
        assert len(boundary.limiter.buckets) == 3
        assert (await exchange(boundary, forbid_read=True))[0] == 429
    asyncio.run(scenario())


def test_fully_replenished_idle_bucket_can_be_reclaimed():
    clock = Clock()
    boundary = rate_boundary(clock, request_rate_limit=1, request_rate_window_seconds=10, request_rate_max_clients=1)
    async def scenario():
        assert (await exchange(boundary))[0] == 204
        assert (await exchange(boundary, client=("127.0.0.2", 1), forbid_read=True))[0] == 429
        clock.now = 10
        assert (await exchange(boundary, client=("127.0.0.2", 1)))[0] == 204
        assert (await exchange(boundary, forbid_read=True))[0] == 429
        assert len(boundary.limiter.buckets) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("peers", [(("127.0.0.1", 1), ("::ffff:127.0.0.1", 2)),
                                  (("::1", 1), ("0:0:0:0:0:0:0:1", 2)),
                                  (None, ("not-an-ip", 1)), (("::1%untrusted", 1), ("x" * 1000, 2))])
def test_equivalent_or_unusable_peer_identities_share_a_bounded_bucket(peers):
    boundary = rate_boundary(Clock(), request_rate_limit=1)
    async def scenario():
        assert (await exchange(boundary, client=peers[0]))[0] == 204
        assert (await exchange(boundary, client=peers[1], forbid_read=True))[0] == 429
        assert len(boundary.limiter.buckets) == 1
    asyncio.run(scenario())


def test_concurrent_quota_updates_are_atomic_and_memory_bounded():
    boundary = rate_boundary(Clock(), request_rate_limit=17, request_rate_max_clients=3)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: boundary.limiter.allow("127.0.0.1"), range(256)))
        distinct = list(pool.map(lambda index: boundary.limiter.allow(f"192.0.2.{index}"), range(100)))
    assert sum(results) == 17 and sum(distinct) == 2
    assert len(boundary.limiter.buckets) == 3
    assert all(0 <= tokens < 17 for tokens, _ in boundary.limiter.buckets.values())


def test_backwards_clock_does_not_grant_tokens_or_extra_future_refill():
    clock = Clock()
    clock.now = 100
    boundary = rate_boundary(clock, request_rate_limit=1, request_rate_window_seconds=10)
    assert boundary.limiter.allow("127.0.0.1")
    for now in (90, 100):
        clock.now = now
        assert not boundary.limiter.allow("127.0.0.1")
    clock.now = 110
    assert boundary.limiter.allow("127.0.0.1")


def test_health_get_and_preflight_are_exempt_but_other_health_methods_are_limited():
    boundary = rate_boundary(Clock(), request_rate_limit=1)
    async def scenario():
        for _ in range(5):
            assert (await exchange(boundary, path="/api/health", method="GET"))[0] == 204
            assert (await exchange(boundary, method="OPTIONS", headers=((b"origin", b"http://localhost:5173"),
                (b"access-control-request-method", b"POST"))))[0] == 204
        assert (await exchange(boundary))[0] == 204
        assert (await exchange(boundary, path="/api/health", method="POST", forbid_read=True))[0] == 429
        assert (await exchange(boundary, path="/api/health", method="GET"))[0] == 204
        assert (await exchange(boundary, method="OPTIONS", headers=((b"access-control-request-method", b"DELETE"),), forbid_read=True))[0] == 422
    asyncio.run(scenario())


@pytest.mark.parametrize("headers,chunks,status", [
    ((), (b"x" * 32, b"y" * 33), 413),
    (((b"transfer-encoding", b"chunked"),), (b"x" * 32, b"y" * 33), 413),
    (((b"content-length", b"1"),), (b"x" * 32, b"y" * 33), 413),
    (((b"content-length", b"bad"),), (b"",), 422),
    (((b"content-length", b"1"), (b"content-length", b"1")), (b"",), 422),
    (((b"content-length", b"1"), (b"transfer-encoding", b"chunked")), (b"",), 422),
    (((b"content-length", b"1"),), (b"{}",), 422),
    (((b"content-encoding", b"gzip"),), (b"",), 422),
])
def test_admitted_requests_preserve_streamed_byte_and_framing_checks(headers, chunks, status):
    boundary = rate_boundary(Clock(), request_rate_limit=2, max_request_body_bytes=64)
    async def scenario():
        assert (await exchange(boundary, headers=headers, chunks=chunks))[0] == status
        assert (await exchange(boundary, chunks=(b"valid",)))[0] == 204
        assert (await exchange(boundary, forbid_read=True))[0] == 429
    asyncio.run(scenario())


def test_http_buffer_admission_is_bounded_and_slots_are_released():
    async def scenario():
        release = asyncio.Event()
        entered = 0

        async def inner(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = RequestBoundary(inner, settings=BackendConfig())

        async def request(block):
            sent = []

            async def receive():
                nonlocal entered
                entered += 1
                if block:
                    await release.wait()
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            await middleware(scope(), receive, send)
            return sent[0]["status"]

        tasks = [asyncio.create_task(request(True)) for _ in range(8)]
        try:
            for _ in range(100):
                if entered == 8:
                    break
                await asyncio.sleep(0)
            assert entered == 8
            assert await request(False) == 429
        finally:
            release.set()
            results = await asyncio.gather(*tasks)
        assert results == [204] * 8
        assert await request(False) == 204

    asyncio.run(scenario())
