"""Bounded replay and fan-out for committed resource notifications."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from ..api_v1.contracts import (
    ResourceChangedNotification,
    ResourceChangeTarget,
    ResourceReconciliationNotification,
)

ReconciliationReason = Literal[
    "epoch_mismatch",
    "invalid_event_id",
    "replay_window_exhausted",
    "counter_ahead",
]
NotificationPayload = ResourceChangedNotification | ResourceReconciliationNotification
TargetFilter = Callable[[ResourceChangeTarget], bool]


class NotificationHubClosedError(RuntimeError):
    """The notification hub no longer accepts subscribers or publications."""


class NotificationSubscriberLimitError(RuntimeError):
    """The fixed subscriber capacity is already in use."""


@dataclass(frozen=True, slots=True)
class NotificationEnvelope:
    """One typed notification with its SSE event identity."""

    event_id: str
    payload: NotificationPayload


class ResourceNotificationSubscription:
    """One cursor over shared replay state without a private event queue."""

    def __init__(
        self,
        hub: ResourceNotificationHub,
        identity: int,
        cursor: int,
        target_filter: TargetFilter,
        pending: Iterable[NotificationEnvelope],
    ) -> None:
        self._hub = hub
        self._identity = identity
        self._cursor = cursor
        self._target_filter = target_filter
        self._pending = deque(pending)
        self._closed = False

    async def next(self) -> NotificationEnvelope:
        """Wait for one matching resource event or bounded reconciliation."""
        if self._closed:
            raise StopAsyncIteration
        return await self._hub._next(self)

    async def close(self) -> None:
        """Remove this subscriber without touching shared demanded work."""
        if self._closed:
            return
        self._closed = True
        await self._hub._unsubscribe(self._identity)

    def __aiter__(self) -> ResourceNotificationSubscription:
        return self

    async def __anext__(self) -> NotificationEnvelope:
        try:
            return await self.next()
        except StopAsyncIteration:
            raise


class ResourceNotificationHub:
    """Publish committed resource identities through bounded shared replay."""

    def __init__(
        self,
        *,
        epoch: str | None = None,
        replay_capacity: int = 256,
        reconciliation_capacity: int = 64,
        current_capacity: int = 256,
        subscriber_capacity: int = 32,
    ) -> None:
        if replay_capacity < 1:
            raise ValueError("notification replay capacity must be positive")
        if reconciliation_capacity < 1:
            raise ValueError("notification reconciliation capacity must be positive")
        if current_capacity < reconciliation_capacity:
            raise ValueError("notification current capacity must cover reconciliation")
        if subscriber_capacity < 1:
            raise ValueError("notification subscriber capacity must be positive")
        selected_epoch = epoch or uuid4().hex
        if len(selected_epoch) != 32 or any(
            character not in "0123456789abcdef" for character in selected_epoch
        ):
            raise ValueError("notification epoch must be 32 lowercase hex characters")
        self.epoch = selected_epoch
        self.replay_capacity = replay_capacity
        self.reconciliation_capacity = reconciliation_capacity
        self.current_capacity = current_capacity
        self.subscriber_capacity = subscriber_capacity
        self._counter = 0
        self._history: deque[ResourceChangedNotification] = deque(
            maxlen=replay_capacity
        )
        self._current: OrderedDict[
            tuple[str, str],
            ResourceChangeTarget,
        ] = OrderedDict()
        self._condition = asyncio.Condition()
        self._subscribers: set[int] = set()
        self._next_subscriber = 1
        self._closed = False

    @property
    def change_counter(self) -> int:
        """Newest assigned change counter."""
        return self._counter

    @property
    def history_size(self) -> int:
        """Number of shared replay records retained."""
        return len(self._history)

    @property
    def subscriber_count(self) -> int:
        """Number of active cursors over the shared replay window."""
        return len(self._subscribers)

    async def publish(
        self,
        targets: Iterable[ResourceChangeTarget],
        *,
        force: bool = False,
        at: float | None = None,
    ) -> tuple[NotificationEnvelope, ...]:
        """Publish newest readable targets and suppress identical cursors."""
        deduplicated: OrderedDict[
            tuple[str, str],
            ResourceChangeTarget,
        ] = OrderedDict()
        for target in targets:
            key = (target.resource_kind, target.resource_id)
            deduplicated[key] = target
            deduplicated.move_to_end(key)
        published: list[NotificationEnvelope] = []
        timestamp = time.time() if at is None else at
        async with self._condition:
            if self._closed:
                raise NotificationHubClosedError("notification hub is closed")
            for key, target in deduplicated.items():
                current = self._current.get(key)
                if (
                    not force
                    and current is not None
                    and current.resource_version == target.resource_version
                    and current.source_cursor == target.source_cursor
                ):
                    continue
                self._counter += 1
                payload = ResourceChangedNotification(
                    server_epoch=self.epoch,
                    change_counter=self._counter,
                    resource_kind=target.resource_kind,
                    resource_id=target.resource_id,
                    resource_version=target.resource_version,
                    source_cursor=target.source_cursor,
                    session_id=target.session_id,
                    player_id=target.player_id,
                    at=timestamp,
                )
                self._history.append(payload)
                self._current[key] = target
                self._current.move_to_end(key)
                while len(self._current) > self.current_capacity:
                    self._current.popitem(last=False)
                published.append(
                    NotificationEnvelope(
                        event_id=self._event_id(self._counter),
                        payload=payload,
                    )
                )
            if published:
                self._condition.notify_all()
        return tuple(published)

    async def subscribe(
        self,
        last_event_id: str | None,
        *,
        target_filter: TargetFilter | None = None,
    ) -> ResourceNotificationSubscription:
        """Open one bounded replay cursor from an optional SSE event id."""
        selected_filter = target_filter or _accept_all
        async with self._condition:
            if self._closed:
                raise NotificationHubClosedError("notification hub is closed")
            if len(self._subscribers) >= self.subscriber_capacity:
                raise NotificationSubscriberLimitError(
                    "notification subscriber capacity is in use"
                )
            cursor, reason = self._resume_cursor(last_event_id)
            pending: tuple[NotificationEnvelope, ...] = ()
            if reason is not None:
                cursor = self._counter
                pending = (self._reconciliation(reason, selected_filter),)
            identity = self._next_subscriber
            self._next_subscriber += 1
            self._subscribers.add(identity)
            return ResourceNotificationSubscription(
                self,
                identity,
                cursor,
                selected_filter,
                pending,
            )

    async def close(self) -> None:
        """Wake all subscribers and reject later publications."""
        async with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _resume_cursor(
        self,
        last_event_id: str | None,
    ) -> tuple[int, ReconciliationReason | None]:
        if last_event_id is None:
            return self._counter, None
        try:
            epoch, raw_counter = last_event_id.split(":", 1)
            counter = int(raw_counter)
        except (TypeError, ValueError):
            return self._counter, "invalid_event_id"
        if counter < 0:
            return self._counter, "invalid_event_id"
        if epoch != self.epoch:
            return self._counter, "epoch_mismatch"
        if counter > self._counter:
            return self._counter, "counter_ahead"
        if self._history and counter < self._history[0].change_counter - 1:
            return self._counter, "replay_window_exhausted"
        return counter, None

    async def _next(
        self,
        subscription: ResourceNotificationSubscription,
    ) -> NotificationEnvelope:
        async with self._condition:
            while True:
                if subscription._pending:
                    return subscription._pending.popleft()
                if subscription._closed or self._closed:
                    raise StopAsyncIteration
                if (
                    self._history
                    and subscription._cursor < self._history[0].change_counter - 1
                ):
                    subscription._cursor = self._counter
                    return self._reconciliation(
                        "replay_window_exhausted",
                        subscription._target_filter,
                    )
                for payload in self._history:
                    if payload.change_counter <= subscription._cursor:
                        continue
                    subscription._cursor = payload.change_counter
                    target = ResourceChangeTarget(
                        resource_kind=payload.resource_kind,
                        resource_id=payload.resource_id,
                        resource_version=payload.resource_version,
                        source_cursor=payload.source_cursor,
                        session_id=payload.session_id,
                        player_id=payload.player_id,
                    )
                    if subscription._target_filter(target):
                        return NotificationEnvelope(
                            event_id=self._event_id(payload.change_counter),
                            payload=payload,
                        )
                await self._condition.wait()

    async def _unsubscribe(self, identity: int) -> None:
        async with self._condition:
            self._subscribers.discard(identity)

    def _reconciliation(
        self,
        reason: ReconciliationReason,
        target_filter: TargetFilter,
    ) -> NotificationEnvelope:
        targets = tuple(
            target for target in self._current.values() if target_filter(target)
        )[-self.reconciliation_capacity :]
        payload = ResourceReconciliationNotification(
            server_epoch=self.epoch,
            change_counter=self._counter,
            reason=reason,
            resources=targets,
            at=time.time(),
        )
        return NotificationEnvelope(
            event_id=self._event_id(self._counter),
            payload=payload,
        )

    def _event_id(self, counter: int) -> str:
        return f"{self.epoch}:{counter}"


def _accept_all(_target: ResourceChangeTarget) -> bool:
    return True
