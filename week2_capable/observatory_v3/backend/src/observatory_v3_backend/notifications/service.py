"""Demand-aware publication after committed session materialization."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..api_v1.contracts import ResourceChangeTarget
from ..index import IndexStore
from ..materialization import (
    MaterializerBusyError,
    MaterializerClosedError,
    SessionMaterializer,
)
from ..repositories import RegistryDatabase
from ..repositories.session_lookup import SessionLookupRepository
from ..resources.repository import ResourceRepository
from ..storage_executor import StorageExecutor
from .hub import NotificationHubClosedError, ResourceNotificationHub
from .targets import CommittedResourceTargets


class NotificationDemandClosedError(RuntimeError):
    """The notification demand service no longer accepts subscriptions."""


class NotificationDemandLimitError(RuntimeError):
    """The bounded selected-session watch capacity is already in use."""


class NotificationSessionNotFoundError(KeyError):
    """The requested selected-session notification scope does not exist."""


class NotificationSeedError(RuntimeError):
    """Initial readable notification targets could not be established."""


@dataclass(slots=True)
class _SessionDemand:
    task: asyncio.Task[None]
    subscribers: int
    changed: asyncio.Event
    ready: asyncio.Event
    seed_error: str | None = None


class SessionNotificationLease:
    """One browser demand reference for a shared selected-session watcher."""

    def __init__(
        self,
        service: SessionNotificationService,
        session_id: str,
    ) -> None:
        self._service = service
        self.session_id = session_id
        self._closed = False

    async def close(self) -> None:
        """Release this browser reference without cancelling shared work."""
        if self._closed:
            return
        self._closed = True
        await self._service._release(self.session_id)

    async def wait_ready(self) -> None:
        """Wait for bounded committed targets before replay reconciliation."""
        await self._service._wait_ready(self.session_id)


class SessionNotificationService:
    """Share bounded source advancement across notification subscribers."""

    def __init__(
        self,
        *,
        registry: RegistryDatabase,
        index: IndexStore,
        resources: ResourceRepository,
        catalog_target: Callable[[], Awaitable[ResourceChangeTarget]],
        materializer: SessionMaterializer,
        storage: StorageExecutor,
        hub: ResourceNotificationHub,
        poll_interval: float = 0.1,
        seed_timeout: float = 5.0,
        session_capacity: int = 16,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("notification poll interval must be positive")
        if session_capacity < 1:
            raise ValueError("notification session capacity must be positive")
        if seed_timeout <= 0:
            raise ValueError("notification seed timeout must be positive")
        self._registry = registry
        self._index = index
        self._lookup = SessionLookupRepository(registry)
        self._materializer = materializer
        self._storage = storage
        self._hub = hub
        self._targets = CommittedResourceTargets(resources)
        self._catalog_target = catalog_target
        self.poll_interval = poll_interval
        self.seed_timeout = seed_timeout
        self.session_capacity = session_capacity
        self._lock = asyncio.Lock()
        self._demands: dict[str, _SessionDemand] = {}
        self._closed = False

    @property
    def active_session_count(self) -> int:
        """Number of selected sessions with a retained demand record."""
        return len(self._demands)

    async def acquire(self, session_id: str) -> SessionNotificationLease:
        """Join or start one selected-session notification watcher."""
        record = await self._storage.run(self._lookup.get, session_id)
        if record is None:
            raise NotificationSessionNotFoundError(session_id)
        async with self._lock:
            if self._closed:
                raise NotificationDemandClosedError(
                    "notification demand service is closed"
                )
            demand = self._demands.get(session_id)
            if demand is None:
                if len(self._demands) >= self.session_capacity:
                    raise NotificationDemandLimitError(
                        "notification session capacity is in use"
                    )
                changed = asyncio.Event()
                ready = asyncio.Event()
                task = asyncio.create_task(
                    self._watch(session_id, changed),
                    name=f"observatory-notifications:{session_id}",
                )
                demand = _SessionDemand(
                    task=task,
                    subscribers=0,
                    changed=changed,
                    ready=ready,
                )
                self._demands[session_id] = demand
            elif demand.task.done():
                demand.changed = asyncio.Event()
                demand.ready = asyncio.Event()
                demand.seed_error = None
                demand.task = asyncio.create_task(
                    self._watch(session_id, demand.changed),
                    name=f"observatory-notifications:{session_id}",
                )
            demand.subscribers += 1
        return SessionNotificationLease(self, session_id)

    async def source_changed(self, session_id: str) -> None:
        """Request one coalesced follow-up for an already demanded session."""
        await self._materializer.notify_source_changed(session_id)
        async with self._lock:
            demand = self._demands.get(session_id)
            if demand is not None:
                demand.changed.set()

    async def close(self) -> None:
        """Stop after in-flight shared work reaches a safe boundary."""
        async with self._lock:
            self._closed = True
            demands = tuple(self._demands.values())
            for demand in demands:
                demand.changed.set()
        if demands:
            await asyncio.gather(
                *(demand.task for demand in demands),
                return_exceptions=True,
            )
        async with self._lock:
            self._demands.clear()

    async def _release(self, session_id: str) -> None:
        async with self._lock:
            demand = self._demands.get(session_id)
            if demand is None:
                return
            demand.subscribers = max(0, demand.subscribers - 1)
            if demand.subscribers == 0:
                demand.changed.set()
                if demand.task.done():
                    self._demands.pop(session_id, None)

    async def _wait_ready(self, session_id: str) -> None:
        async with self._lock:
            demand = self._demands.get(session_id)
            if demand is None:
                raise NotificationSeedError("notification demand disappeared")
            ready = demand.ready
        try:
            await asyncio.wait_for(ready.wait(), timeout=self.seed_timeout)
        except TimeoutError as error:
            raise NotificationSeedError(
                "notification target seeding timed out"
            ) from error
        async with self._lock:
            demand = self._demands.get(session_id)
            seed_error = None if demand is None else demand.seed_error
        if seed_error is not None:
            raise NotificationSeedError(seed_error)

    async def _watch(
        self,
        session_id: str,
        changed: asyncio.Event,
    ) -> None:
        first = True
        try:
            while True:
                try:
                    result = await self._materializer.materialize(session_id)
                except (
                    KeyError,
                    MaterializerBusyError,
                    MaterializerClosedError,
                ) as error:
                    await self._seed_failed(session_id, str(error))
                    return
                except Exception:
                    await self._publish_cold_fault(session_id)
                    return
                if result.fault is None:
                    if first or result.kind != "unchanged":
                        await self._storage.run(
                            self._index.clear_materialization_fault,
                            session_id,
                        )
                else:
                    await self._storage.run(
                        self._index.record_materialization_fault,
                        session_id,
                        f"Selected-session materialization failed: {result.fault}.",
                    )
                if first or result.kind != "unchanged":
                    targets = (
                        await self._catalog_target(),
                        *await self._storage.run(
                            self._targets.for_session,
                            session_id,
                        ),
                    )
                    try:
                        await self._hub.publish(
                            targets,
                            force=result.fault is not None or result.terminal,
                        )
                    except NotificationHubClosedError:
                        await self._seed_failed(
                            session_id,
                            "notification hub closed during target seeding",
                        )
                        return
                    await self._seed_ready(session_id)
                first = False
                if result.terminal or result.fault is not None:
                    return
                changed.clear()
                try:
                    await asyncio.wait_for(
                        changed.wait(),
                        timeout=self.poll_interval,
                    )
                except TimeoutError:
                    pass
                async with self._lock:
                    demand = self._demands.get(session_id)
                    if self._closed or demand is None or demand.subscribers == 0:
                        return
        finally:
            async with self._lock:
                demand = self._demands.get(session_id)
                if (
                    demand is not None
                    and demand.task is asyncio.current_task()
                    and demand.subscribers == 0
                ):
                    self._demands.pop(session_id, None)

    async def _publish_cold_fault(self, session_id: str) -> None:
        try:
            await self._storage.run(
                self._index.record_materialization_fault,
                session_id,
                "Selected-session materialization failed validation.",
            )
            target = await self._catalog_target()
            await self._hub.publish((target,), force=True)
        except Exception as error:
            await self._seed_failed(session_id, str(error))
            return
        await self._seed_ready(session_id)

    async def _seed_ready(self, session_id: str) -> None:
        async with self._lock:
            demand = self._demands.get(session_id)
            if demand is not None:
                demand.ready.set()

    async def _seed_failed(self, session_id: str, detail: str) -> None:
        async with self._lock:
            demand = self._demands.get(session_id)
            if demand is not None:
                demand.seed_error = detail or "notification target seeding failed"
                demand.ready.set()
