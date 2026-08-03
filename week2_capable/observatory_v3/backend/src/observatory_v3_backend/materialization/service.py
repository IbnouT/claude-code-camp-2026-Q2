"""Bounded singleflight orchestration for selected-session materialization."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from ..index.store import IndexProjectionConflict, IndexStore
from ..repositories import RegistryDatabase
from ..storage_executor import StorageExecutor
from .advance import IncrementalSessionAdvancer
from .models import AdvanceMetrics, MaterializationResult


class MaterializerBusyError(RuntimeError):
    """The bounded materialization queue has no remaining capacity."""


class MaterializerClosedError(RuntimeError):
    """The materializer no longer accepts work."""


class SessionAdvancer(Protocol):
    """Synchronous advancement boundary used by the worker service."""

    def advance(self, session_id: str) -> MaterializationResult:
        """Advance one session synchronously."""
        ...


@dataclass(slots=True)
class _Flight:
    """The shared task owned by one selected session."""

    task: asyncio.Task[MaterializationResult]
    changed: bool = False


class SessionMaterializer:
    """Materialize selected sessions on demand with bounded shared work."""

    def __init__(
        self,
        registry: RegistryDatabase,
        index: IndexStore,
        *,
        workers: int = 4,
        queue_capacity: int = 16,
        max_catch_up_passes: int = 8,
        conflict_retries: int = 2,
        advancer: SessionAdvancer | None = None,
        storage: StorageExecutor | None = None,
    ) -> None:
        if workers < 1:
            raise ValueError("materializer workers must be positive")
        if queue_capacity < 0:
            raise ValueError("materializer queue capacity cannot be negative")
        if max_catch_up_passes < 1:
            raise ValueError("materializer catch-up passes must be positive")
        if conflict_retries < 0:
            raise ValueError("materializer retries cannot be negative")
        self._advancer = advancer or IncrementalSessionAdvancer(registry, index)
        self._storage = storage or StorageExecutor(capacity=workers)
        self._owns_storage = storage is None
        self._slots = asyncio.Semaphore(workers)
        self._maximum_flights = workers + queue_capacity
        self._max_catch_up_passes = max_catch_up_passes
        self._conflict_retries = conflict_retries
        self._lock = asyncio.Lock()
        self._flights: dict[str, _Flight] = {}
        self._closed = False

    async def materialize(self, session_id: str) -> MaterializationResult:
        """Join or start one selected-session advancement."""
        async with self._lock:
            if self._closed:
                raise MaterializerClosedError("materializer is closed")
            flight = self._flights.get(session_id)
            if flight is None:
                if len(self._flights) >= self._maximum_flights:
                    raise MaterializerBusyError("materialization queue is at capacity")
                task = asyncio.create_task(
                    self._run_flight(session_id),
                    name=f"observatory-materialize:{session_id}",
                )
                flight = _Flight(task=task)
                self._flights[session_id] = flight
            task = flight.task
        return await asyncio.shield(task)

    async def notify_source_changed(self, session_id: str) -> None:
        """Coalesce a source-change signal into one demanded follow-up pass."""
        async with self._lock:
            flight = self._flights.get(session_id)
            if flight is not None:
                flight.changed = True

    async def close(self) -> None:
        """Stop accepting work, drain shared tasks, and release workers."""
        async with self._lock:
            self._closed = True
            tasks = tuple(flight.task for flight in self._flights.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._owns_storage:
            await self._storage.close()

    async def _run_flight(self, session_id: str) -> MaterializationResult:
        current_task = asyncio.current_task()
        result: MaterializationResult | None = None
        try:
            async with self._slots:
                result = await self._advance_until_caught_up(session_id)
                async with self._lock:
                    flight = self._flights[session_id]
                    follow_up = flight.changed
                    flight.changed = False
                if follow_up:
                    result = await self._advance_until_caught_up(session_id)
                return result
        finally:
            async with self._lock:
                completed_flight = self._flights.get(session_id)
                if (
                    completed_flight is not None
                    and completed_flight.task is current_task
                ):
                    if (
                        result is not None
                        and completed_flight.changed
                        and not self._closed
                    ):
                        completed_flight.changed = False
                        completed_flight.task = asyncio.create_task(
                            self._run_flight(session_id),
                            name=f"observatory-materialize:{session_id}",
                        )
                    else:
                        self._flights.pop(session_id, None)

    async def _advance_until_caught_up(
        self,
        session_id: str,
    ) -> MaterializationResult:
        combined: MaterializationResult | None = None
        for _pass in range(1, self._max_catch_up_passes + 1):
            result = await self._advance_with_retry(session_id)
            combined = _combine(combined, result)
            if result.terminal or not result.more_available:
                return combined
        if combined is None:
            raise RuntimeError("materializer completed no advancement")
        return combined

    async def _advance_with_retry(
        self,
        session_id: str,
    ) -> MaterializationResult:
        for attempt in range(self._conflict_retries + 1):
            try:
                return await self._storage.run(
                    self._advancer.advance,
                    session_id,
                )
            except IndexProjectionConflict:
                if attempt >= self._conflict_retries:
                    raise
                await asyncio.sleep(0)
        raise RuntimeError("materializer retry loop did not return")


def _combine(
    previous: MaterializationResult | None,
    current: MaterializationResult,
) -> MaterializationResult:
    if previous is None:
        return current
    return MaterializationResult(
        session_id=current.session_id,
        cursor=current.cursor,
        generation=current.generation,
        kind=previous.kind if current.kind == "unchanged" else current.kind,
        terminal=current.terminal,
        more_available=current.more_available,
        fault=current.fault,
        metrics=AdvanceMetrics(
            agent_start_offset=previous.metrics.agent_start_offset,
            agent_records=(
                previous.metrics.agent_records + current.metrics.agent_records
            ),
            gateway_after_sequence=previous.metrics.gateway_after_sequence,
            gateway_records=(
                previous.metrics.gateway_records + current.metrics.gateway_records
            ),
            lifecycle_after_sequence=previous.metrics.lifecycle_after_sequence,
            lifecycle_records=(
                previous.metrics.lifecycle_records + current.metrics.lifecycle_records
            ),
            passes=previous.metrics.passes + current.metrics.passes,
        ),
    )
