"""Concurrency and cancellation gates for synchronous retained-source work."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path

import anyio
import httpx
import pytest

from observatory_v3_backend.app import create_app
from observatory_v3_backend.settings import Settings
from observatory_v3_backend.sources.benchmark import BenchmarkSource
from observatory_v3_backend.storage_executor import StorageExecutor


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_storage_work_is_bounded_and_keeps_event_loop_responsive() -> None:
    executor = StorageExecutor(capacity=2)
    lock = threading.Lock()
    active = 0
    peak = 0
    delays: list[float] = []

    def slow_read() -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        with lock:
            active -= 1

    async def measure_loop() -> None:
        previous = anyio.current_time()
        for _ in range(20):
            await anyio.sleep(0.005)
            current = anyio.current_time()
            delays.append(current - previous - 0.005)
            previous = current

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(measure_loop)
        for _ in range(12):
            tasks.start_soon(executor.run, slow_read)

    assert peak == 2
    ordered = sorted(delays)
    p95 = ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)]
    assert p95 < 0.025
    await executor.close()


@pytest.mark.anyio
async def test_cancelled_storage_waiter_returns_without_waiting_for_thread() -> None:
    executor = StorageExecutor(capacity=1)
    release = threading.Event()
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def blocked_read() -> None:
        loop.call_soon_threadsafe(started.set)
        release.wait(timeout=1)

    async def cancel_after_start(cancel: Callable[[], None]) -> None:
        await started.wait()
        cancel()

    began = anyio.current_time()
    try:
        with anyio.CancelScope() as scope:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(cancel_after_start, scope.cancel)
                await executor.run(blocked_read)
    finally:
        release.set()

    assert anyio.current_time() - began < 0.1
    await executor.close()


@pytest.mark.anyio
async def test_cancelled_calls_never_exceed_the_worker_capacity() -> None:
    executor = StorageExecutor(capacity=1)
    lock = threading.Lock()
    active = 0
    peak = 0

    def slow_read() -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        with lock:
            active -= 1

    for _ in range(8):
        with anyio.move_on_after(0.005):
            await executor.run(slow_read)

    await executor.close()

    assert peak == 1


@pytest.mark.anyio
async def test_runs_route_keeps_slow_storage_off_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow_runs(_source: BenchmarkSource) -> tuple[object, ...]:
        time.sleep(0.04)
        return ()

    monkeypatch.setattr(BenchmarkSource, "runs", slow_runs)
    application = create_app(
        Settings(
            web_dist=tmp_path,
            benchmark_root=tmp_path,
        )
    )
    delays: list[float] = []
    status_code = 0

    async def request_runs(client: httpx.AsyncClient) -> None:
        nonlocal status_code
        status_code = (await client.get("/api/runs")).status_code

    async def sample_loop() -> None:
        previous = anyio.current_time()
        for _ in range(50):
            await anyio.sleep(0.001)
            current = anyio.current_time()
            delays.append(current - previous - 0.001)
            previous = current

    transport = httpx.ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://observatory.test",
        ) as client:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(request_runs, client)
                tasks.start_soon(sample_loop)

    ordered = sorted(delays)
    p95 = ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)]
    assert status_code == 200
    assert p95 < 0.025
