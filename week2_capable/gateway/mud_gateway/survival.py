"""The survival capability's reflex engine.

Standing behaviors enforced by the harness on typed numbers, never on
prose: keep the game's own auto-flee threshold set, and rest before
movement depletes. Every reflex firing is journaled with its rule id and
the numbers that triggered it, so the Observatory explains each one like
any other decision.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

RULES_VERSION = "survival-1"


class Survival:
    """Numeric reflexes bound to one session and its knowledge store."""

    def __init__(
        self,
        session: Any,
        store: Any,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        block = dict(settings or {})
        self.session = session
        self.store = store
        self.wimpy_fraction = float(block.get("wimpy_fraction", 0.3))
        self.rest_threshold = float(block.get("rest_threshold", 0.2))
        self.rest_resume = float(block.get("rest_resume", 0.8))
        self.rest_poll_seconds = float(block.get("rest_poll_seconds", 6.0))
        self.rest_max_polls = int(block.get("rest_max_polls", 20))

    # -- store reads -------------------------------------------------------

    def player_maximum(self, name: str) -> int | None:
        """One of the player's parsed maxima, or None when never observed."""
        predicate = f"state.max_{name}"
        for fact in self.store.current_facts(layer="parsed"):
            if fact.subject.startswith("player:") \
                    and fact.predicate == predicate \
                    and isinstance(fact.value, int):
                return fact.value
        return None

    def _journal(self, rule: str, payload: dict[str, Any]) -> None:
        self.session.journal.append(
            self.session.id,
            "reflex",
            {"rule": rule, "version": RULES_VERSION, **payload},
        )

    # -- reflexes ----------------------------------------------------------

    async def apply_wimpy(self) -> int | None:
        """Set the game's own auto-flee threshold from observed maximum hp."""
        max_hit = self.player_maximum("hit")
        if max_hit is None:
            self._journal("wimpy", {"applied": False, "reason": "no_max_hit"})
            return None
        threshold = max(1, int(max_hit * self.wimpy_fraction))
        await self.session.command(f"wimpy {threshold}")
        self._journal(
            "wimpy",
            {"applied": True, "threshold": threshold, "max_hit": max_hit},
        )
        return threshold

    async def recover_movement(
        self,
        current_move: int | None,
        trace_id: str | None = None,
    ) -> str | None:
        """Rest until movement recovers, when it has fallen too low.

        Returns None when no rest was needed, "rested" after a successful
        recovery, and "rest_timeout" when the bounded wait expired.
        """
        max_move = self.player_maximum("move")
        if max_move is None or current_move is None:
            return None
        floor = max_move * self.rest_threshold
        if current_move > floor:
            return None
        target = max_move * self.rest_resume
        self._journal(
            "rest",
            {
                "phase": "start",
                "move": current_move,
                "floor": int(floor),
                "target": int(target),
            },
        )
        await self.session.command("rest", trace_id=trace_id)
        for _ in range(self.rest_max_polls):
            await asyncio.sleep(self.rest_poll_seconds)
            reply = await self.session.command("score", trace_id=trace_id)
            move = _latest_move(reply)
            if move is not None and move >= target:
                await self.session.command("stand", trace_id=trace_id)
                self._journal("rest", {"phase": "recovered", "move": move})
                return "rested"
        await self.session.command("stand", trace_id=trace_id)
        self._journal("rest", {"phase": "timeout"})
        return "rest_timeout"


def _latest_move(reply: Any) -> int | None:
    for observation in reply.observations:
        move = getattr(observation, "move", None)
        if isinstance(move, int):
            return move
    return None
