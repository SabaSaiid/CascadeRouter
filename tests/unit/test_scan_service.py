"""Cancelled coroutines retain admission until underlying compiler work exits."""

import asyncio
import threading

import pytest

from backend.services import compiler_adapter
from backend.services.errors import ServiceError
from backend.services.scan_service import ScanService


def test_cancellation_does_not_kill_thread_or_release_its_capacity(api_environment, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = compiler_adapter.analyze_for_api

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(10), "Compiler test thread was not released."
        return original(*args, **kwargs)

    monkeypatch.setattr(compiler_adapter, "analyze_for_api", slow)
    service = ScanService(api_environment[0])

    async def scenario():
        import time
        task = asyncio.create_task(service.scan("repository", time.monotonic() + 20))
        try:
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(ServiceError) as error:
                await service.scan("repository", time.monotonic() + 20)
            assert error.value.code == "capacity_exceeded"
        finally:
            release.set()
            if not task.done():
                await task
            # Wait for the worker callback while the wrapping event loop lives.
            for _ in range(200):
                if service.slots.acquire(blocking=False):
                    service.slots.release()
                    break
                await asyncio.sleep(0.005)
            else:
                pytest.fail("Compiler worker did not finish after release.")

    try:
        asyncio.run(scenario())
    finally:
        release.set()
        service.close()
