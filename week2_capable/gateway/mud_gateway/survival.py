"""The survival capability's reflex engine.

Standing behaviors enforced by the harness on typed numbers, never on
prose: keep the game's own auto-flee threshold set, and rest before
movement depletes. Every reflex firing is journaled with its rule id and
the numbers that triggered it, so the Observatory explains each one like
any other decision.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Mapping

RULES_VERSION = "survival-1"

# One switch and its state, as the game lists them: "AutoLoot: ON".
TOGGLE_ENTRY = re.compile(r"([A-Za-z]+):\s*(ON|OFF)\b", re.I)


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
        self.game_toggles = tuple(
            # Spelled as the game's own help spells them, and limited to
            # what is safe to send blind. These two report "enabled" when
            # set, so sending them once is idempotent in effect. The exit
            # display is a plain toggle with no way to ask for "on", so
            # sending it would turn off the very lines the parser reads.
            block.get("game_toggles", ("autoloot", "autogold"))
        )

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

    async def let_the_game_do_the_work(self) -> tuple[str, ...]:
        """Turn on the game's own conveniences, without turning any off.

        The game will pick up coins and loot a corpse by itself, which
        saves a decision after every kill. These are switches and they are
        remembered between sessions, so sending one blindly turns off what
        was already on. The game lists them when asked, so what is already
        set is read first and only what is missing is changed.
        """
        current = await self._toggle_states()
        changed = []
        for name in self.game_toggles:
            state = current.get(name.casefold())
            if state is True:
                continue
            if state is None:
                # Unknown state, so changing it could as easily turn the
                # thing off. Left alone and recorded.
                self._journal("game-settings", {"unknown": name})
                continue
            await self.session.command(name)
            changed.append(name)
        self._journal(
            "game-settings", {"turned_on": changed, "already_on": [
                name for name in self.game_toggles
                if current.get(name.casefold()) is True
            ]},
        )
        return tuple(changed)

    async def _toggle_states(self) -> dict[str, bool]:
        """What the game says each of its switches is set to."""
        reply = await self.session.command("toggle")
        found: dict[str, bool] = {}
        for match in TOGGLE_ENTRY.finditer(reply.text):
            found[match.group(1).casefold()] = (
                match.group(2).casefold() == "on"
            )
        return found

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
