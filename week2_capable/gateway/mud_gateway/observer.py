"""The game's own room number, read on a connection the agent never has.

A room has a unique number and the game will state it, so nothing needs
to be inferred from what a room looks like. An immortal connection joins
the session, stays invisible, and answers where the character is. The
number is recorded beside what was observed and is never part of what the
agent is shown.

The observer only ever asks. It issues no command that changes anything.
"""

from __future__ import annotations

from typing import Any

from .admin import AdminSession
from .journal import Journal

#: Level an immortal is hidden at. Anyone below it cannot see the observer
#: in the room, in ``where``, or as something to attack.
INVISIBILITY = 34


class RoomObserver:
    """Answers which room the character is in, or nothing at all.

    Every failure is a shrug: a run without an observer plays exactly as
    it does without one, so no answer here ever stops the game.
    """

    def __init__(
        self,
        journal: Journal,
        *,
        character: str,
        password: str | None,
        host: str,
        port: int,
        watching: str,
        session_id: str,
    ) -> None:
        self.journal = journal
        self.character = character
        self.password = password
        self.host = host
        self.port = port
        self.watching = watching
        self.session_id = session_id
        self.session: AdminSession | None = None
        self.asked = 0
        self.answered = 0
        #: Where the character ended up when it moved mid-reading.
        self.moved_to: int | None = None

    @property
    def available(self) -> bool:
        return self.session is not None

    async def open(self) -> bool:
        """Join the session and go unseen. False when it cannot."""
        if not self.password:
            self._note("unavailable", {"reason": "no immortal password"})
            return False
        session = AdminSession(
            self.journal,
            name=self.character,
            password=self.password,
            host=self.host,
            port=self.port,
            session_id=self.session_id,
        )
        try:
            await session.open()
            # Invisibility is saved on the character, and a bare toggle
            # would undo it. The level is stated so the observer is hidden
            # whatever state the character was left in.
            await session.set_field(self.character, "invis", str(INVISIBILITY))
        except Exception as error:
            self._note("unavailable", {"reason": str(error)})
            try:
                await session.close()
            except Exception:  # pragma: no cover - closing a broken session
                pass
            return False
        self.session = session
        self._note("watching", {"character": self.watching})
        return True

    async def room_number(self) -> int | None:
        """Where the game says the character is, or None.

        Asked twice and believed only when both answers agree. The game
        can move a character on its own, by death, by recall, or by a
        trap, and an answer that straddles such a move would attach what
        was seen in one room to another. Two agreeing answers bracket the
        reading rather than merely precede it.
        """
        self.moved_to = None
        first = await self._locate()
        if first is None:
            return None
        second = await self._locate()
        if second is None:
            return None
        self.answered += 1
        if second != first:
            # The game moved the character between the two answers. Both
            # rooms are real: the reply being recorded was read in the
            # first, and the character now stands in the second. Both are
            # kept, and the caller is told where it ended up.
            self._note("moved", {"from": first, "to": second})
            self.moved_to = second
            return first
        self.moved_to = None
        return first

    async def _locate(self, retry: int = 1) -> int | None:
        session = self.session
        if session is None:
            return None
        self.asked += 1
        try:
            located = await session.locate(self.watching)
        except Exception as error:
            # A lost observer must never end a run, whatever the failure
            # was. The common cause is the reset logging in as the same
            # immortal, which the game answers by closing this connection,
            # and that arrives as a transport error rather than an admin
            # one. Nothing raised here is worth failing a mortal command.
            self._note("lost", {"reason": str(error)})
            await self._drop(session)
            if not await self._reopen() or retry <= 0:
                return None
            # Reconnecting is only worth doing if the question still gets
            # an answer, so the one that was lost is asked again.
            return await self._locate(retry - 1)
        return None if located is None else located[0]

    async def _drop(self, session: Any) -> None:
        """Let go of a broken connection without leaking its socket."""
        self.session = None
        try:
            await session.close()
        except Exception:  # pragma: no cover - closing a broken session
            pass

    async def _reopen(self) -> bool:
        try:
            return await self.open()
        except Exception as error:  # pragma: no cover - instrumentation only
            self._note("unavailable", {"reason": str(error)})
            return False

    async def close(self) -> None:
        session, self.session = self.session, None
        if session is None:
            return
        try:
            await session.close()
        except Exception:  # pragma: no cover - closing a broken session
            pass
        self._note("closed", {"asked": self.asked, "answered": self.answered})

    def _note(self, phase: str, payload: dict[str, Any]) -> None:
        self.journal.append(
            self.session_id, "observer", {"phase": phase, **payload}
        )
