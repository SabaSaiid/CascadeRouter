"""Body deadlines and aggregate admission without sockets or pytest plugins."""

import asyncio
import json

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
