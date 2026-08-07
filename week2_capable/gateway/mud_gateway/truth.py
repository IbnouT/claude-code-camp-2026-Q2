"""Observer truth: the game's own room number, recorded beside what we saw.

The agent never reads this. It exists so a claim about the map can be
checked against the game rather than against our own conclusions: which
observed places really were one room, and whether a walk arrived where
it meant to.

The answer key is kept in a file of its own, outside the store the agent
reads from. That is a stronger guarantee than filtering it out on the
way in: what is not there cannot leak, whatever a future reader forgets
to exclude. Grading joins the two afterwards, which is the only moment
both are needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RoomNumbers:
    """Records the game's room number for the place just observed."""

    def __init__(self, admin: Any, path: Path, character: str) -> None:
        self.admin = admin
        self.path = Path(path)
        self.character = character
        self.recorded = 0
        self.skipped = 0

    async def observe(
        self,
        place_id: str | None,
        session_id: str = "",
        expected_title: str | None = None,
    ) -> int | None:
        """Record where the game says the character is, when it is settled.

        The number is read twice, and where the room just parsed is known
        the answer must name that room. A character that fled, died, or
        was sent elsewhere between the parse and the reading has no single
        answer for the place it was standing in, so nothing is recorded.
        Recording the wrong room here would poison the very measurement
        this exists to provide.
        """
        if place_id is None:
            return None
        first = await self.admin.locate(self.character)
        second = await self.admin.locate(self.character)
        if first is None or second is None or first[0] != second[0]:
            self.skipped += 1
            return None
        if expected_title is not None and (
            first[1].casefold() != expected_title.casefold()
        ):
            self.skipped += 1
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as sink:
            sink.write(json.dumps({
                "session": session_id,
                "place": place_id,
                "room_number": first[0],
                "room_title": first[1],
            }) + "\n")
        self.recorded += 1
        return first[0]
