"""Async supervision for durable lifecycle commands."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable

from .effects import CommandEffects
from .models import Command, CommandSubmission
from .store import CommandStore

CommandObserver = Callable[[Command], Awaitable[None]]
CommandResultPreparer = Callable[[Command, str | None], Awaitable[None]]


class CommandNotFoundError(KeyError):
    """The selected durable command does not exist."""


class CommandConflictError(RuntimeError):
    """The mutation conflicts with retained or current state."""


class CommandUnavailableError(RuntimeError):
    """The command supervisor cannot accept more work."""


class CommandService:
    """Persist, schedule, recover, and expose bounded command state."""

    def __init__(
        self,
        store: CommandStore,
        effects: CommandEffects,
        *,
        observer: CommandObserver | None = None,
        prepare_result: CommandResultPreparer | None = None,
        capacity: int = 64,
    ) -> None:
        self.store = store
        self.effects = effects
        self.observer = observer
        self.prepare_result = prepare_result
        self.capacity = capacity
        self._queue: asyncio.Queue[tuple[str, bool] | None] = asyncio.Queue(
            maxsize=capacity
        )
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._worker = asyncio.create_task(self._run())
        try:
            recoverable = await asyncio.to_thread(self.store.recoverable)
        except sqlite3.Error as error:
            await self.close()
            raise CommandUnavailableError(
                "durable command storage is unavailable"
            ) from error
        if len(recoverable) > self.capacity:
            await self.close()
            raise CommandUnavailableError(
                "recoverable commands exceed supervisor capacity"
            )
        try:
            for command in recoverable:
                self._queue.put_nowait((command.id, True))
        except asyncio.QueueFull as error:
            await self.close()
            raise CommandUnavailableError(
                "recoverable commands exceed supervisor capacity"
            ) from error

    async def close(self) -> None:
        if self._worker is None:
            return
        await self._queue.put(None)
        await self._worker
        self._worker = None

    async def submit(self, value: CommandSubmission) -> Command:
        try:
            existing = await asyncio.to_thread(self.store.existing, value)
            if existing is not None:
                return existing
            await asyncio.to_thread(self.effects.validate, value)
            command, created = await asyncio.to_thread(self.store.submit, value)
        except (ValueError, RuntimeError) as error:
            raise CommandConflictError(str(error)) from error
        except sqlite3.Error as error:
            raise CommandUnavailableError(
                "durable command storage is unavailable"
            ) from error
        if created:
            await self._notify(command)
            try:
                self._queue.put_nowait((command.id, False))
            except asyncio.QueueFull as error:
                failed = await asyncio.to_thread(
                    self.store.transition,
                    command.id,
                    "failed",
                    result_code="supervisor_capacity",
                    result_detail="command supervisor capacity is exhausted",
                )
                await self._notify(failed)
                raise CommandUnavailableError(
                    "command supervisor capacity is exhausted"
                ) from error
        return command

    async def get(self, command_id: str) -> Command:
        try:
            return await asyncio.to_thread(self.store.get, command_id)
        except KeyError as error:
            raise CommandNotFoundError(command_id) from error
        except sqlite3.Error as error:
            raise CommandUnavailableError(
                "durable command storage is unavailable"
            ) from error

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            command_id, recovering = item
            try:
                running = await asyncio.to_thread(
                    self.store.transition,
                    command_id,
                    "running",
                )
            except sqlite3.Error:
                continue
            await self._notify(running)
            try:
                apply = self.effects.reconcile if recovering else self.effects.apply
                session_id = await asyncio.to_thread(apply, running)
            except Exception as error:
                try:
                    terminal = await asyncio.to_thread(
                        self.store.transition,
                        command_id,
                        "failed",
                        result_code="command_failed",
                        result_detail=str(error)[:500],
                    )
                except sqlite3.Error:
                    continue
            else:
                try:
                    if self.prepare_result is not None:
                        await self.prepare_result(running, session_id)
                    terminal = await asyncio.to_thread(
                        self.store.transition,
                        command_id,
                        "succeeded",
                        result_code="applied",
                        result_detail="command applied",
                        result_session_id=session_id,
                    )
                except Exception as error:
                    try:
                        terminal = await asyncio.to_thread(
                            self.store.transition,
                            command_id,
                            "failed",
                            result_code="result_preparation_failed",
                            result_detail=str(error)[:500],
                        )
                    except sqlite3.Error:
                        continue
            await self._notify(terminal)

    async def _notify(self, command: Command) -> None:
        if self.observer is not None:
            await self.observer(command)
