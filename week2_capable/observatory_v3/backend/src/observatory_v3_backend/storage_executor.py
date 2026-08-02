"""Bounded off-loop execution for synchronous backend work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class StorageExecutor:
    """Run synchronous backend work behind one bounded capacity limiter."""

    def __init__(self, *, capacity: int = 8) -> None:
        if capacity < 1:
            raise ValueError("storage capacity must be positive")
        self._pool = ThreadPoolExecutor(
            max_workers=capacity,
            thread_name_prefix="observatory-storage",
        )

    async def run(
        self,
        function: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Run one call off loop and abandon its result after cancellation."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._pool,
            partial(function, *args, **kwargs),
        )

    async def close(self) -> None:
        """Drain running work and release the owned worker pool."""
        await asyncio.to_thread(
            self._pool.shutdown,
            wait=True,
            cancel_futures=True,
        )
