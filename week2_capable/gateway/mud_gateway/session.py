"""A logged-in session: the login sequence, one command at a time, everything journalled.

Sits above the transport and below the parser. It owns the login handshake and the reply
window, and it writes every byte and every command into the journal so that anything derived
later can be traced back.

THE LOGIN SEQUENCE HAS FOUR STEPS, NOT TWO. Name, then password, then a MOTD that waits on a
keypress, then a MENU where ``1`` enters the game. Sending newlines at the menu loops until the
bound runs out. The recorded corpus contains three tool results whose last line is that menu,
which is the same trap reached by accident, so the sequence is written out explicitly rather
than treated as a detail.

THE REPLY WINDOW IS DRAINED BEFORE EACH COMMAND. Unsolicited output ends in a prompt like any
other reply, so anything left in the buffer satisfies the next read and every reply after it
arrives shifted by one. Draining is not discarding: what arrives unbidden is journalled as its
own event, because the world acting on its own is a fact and not noise.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass

from .journal import Journal
from .wire import PROMPT, Direction, Transport, WireEvent, strip_ansi

#: Login prompts, matched loosely because the banner wording changes between builds.
NAME_PROMPT = re.compile(rb"by what name|name:", re.I)
PASSWORD_PROMPT = re.compile(rb"password", re.I)
MENU_PROMPT = re.compile(rb"make your choice", re.I)
WRONG_PASSWORD = re.compile(rb"wrong password", re.I)

#: The menu option that enters the game.
ENTER_GAME = "1"

#: How many times the entry sequence may answer a prompt before giving up. A wrong password
#: re-prompts rather than erroring, so this has to be bounded.
ENTRY_STEPS = 6


class LoginFailed(Exception):
    pass


@dataclass
class Reply:
    """One command and the bytes it produced, plus anything that arrived unbidden first."""

    command: str
    raw: bytes
    unsolicited: bytes
    complete: bool
    seq: int

    @property
    def text(self) -> str:
        return strip_ansi(self.raw).decode("latin-1").replace("\r", "")

    def __str__(self) -> str:
        preview = " ".join(self.text.split())[:50]
        extra = "" if not self.unsolicited else f" unsolicited={len(self.unsolicited)}"
        return (f"<Reply {self.command!r} bytes={len(self.raw)} complete={self.complete}"
                f"{extra} text={preview!r}>")


class Session:
    """One character's connection to the game.

    Every wire event is journalled as it happens, and every command is journalled with the
    sequence number of the reply it produced, so a later question about why something happened
    has an answer rather than a reconstruction.
    """

    def __init__(self, journal: Journal, *, name: str, password: str,
                 host: str = "127.0.0.1", port: int = 4000, timeout: float = 25.0,
                 session_id: str | None = None) -> None:
        self.id = session_id or f"{name}-{uuid.uuid4().hex[:8]}"
        self.name = name
        self._password = password
        self.journal = journal
        self.transport = Transport(host=host, port=port, timeout=timeout,
                                  on_wire=self._journal_wire)
        self._logged_in = False
        self._command_lock = asyncio.Lock()
        self.trace_id: str | None = None

    # -- lifecycle ----------------------------------------------------------

    async def open(self) -> None:
        """Connect and walk the whole entry sequence."""
        await self.transport.connect()
        self.journal.append(self.id, "session_open",
                            {"character": self.name,
                             "host": self.transport.host, "port": self.transport.port})
        # The greeting requires its pattern rather than accepting silence: the server sends a
        # client-detection notice and then pauses while it probes.
        await self.transport.read_until(NAME_PROMPT, quiet=None, deadline=self.transport.timeout)
        await self.transport.send(self.name)
        await self.transport.read_until(PASSWORD_PROMPT, quiet=None)
        await self.transport.send(self._password, secret=True)

        seen = await self.transport.read_until(PROMPT, quiet=1.5)
        for _ in range(ENTRY_STEPS):
            if WRONG_PASSWORD.search(seen):
                self.journal.append(self.id, "login_failed", {"character": self.name})
                raise LoginFailed(f"password rejected for {self.name!r}")
            if PROMPT.search(seen):
                self._logged_in = True
                self.journal.append(self.id, "login", {"character": self.name})
                return
            await self.transport.send(ENTER_GAME if MENU_PROMPT.search(seen) else "")
            seen += await self.transport.read_until(PROMPT, quiet=1.2)
        self.journal.append(self.id, "login_failed",
                            {"character": self.name, "reason": "no prompt"})
        raise LoginFailed(f"no prompt after login as {self.name!r}")

    async def close(self) -> None:
        if self._logged_in and not self.transport.closed:
            try:
                await self.command("quit")
            except Exception:
                pass
        await self.transport.close()
        self._logged_in = False
        self.journal.append(self.id, "session_close", {"character": self.name})

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    # -- commands -----------------------------------------------------------

    async def command(self, line: str, *, trace_id: str | None = None) -> Reply:
        """Send one line and collect its reply, with the window aligned first."""
        async with self._command_lock:
            trace = trace_id or self.trace_id
            pending = await self.transport.drain_pending()
            if pending:
                self.journal.append(self.id, "unsolicited",
                                    {"bytes": len(pending),
                                     "text": strip_ansi(pending).decode("latin-1")},
                                    trace_id=trace)
            await self.transport.send(line)
            raw = await self.transport.read_until(PROMPT, quiet=0.6)
            event = self.journal.append(
                self.id, "command",
                {"line": line, "reply_bytes": len(raw),
                 "complete": bool(PROMPT.search(raw)),
                 "unsolicited_bytes": len(pending)},
                trace_id=trace)
            return Reply(command=line, raw=raw, unsolicited=pending,
                         complete=bool(PROMPT.search(raw)), seq=event.seq)

    # -- internals ----------------------------------------------------------

    def _journal_wire(self, event: WireEvent) -> None:
        """Every byte, both directions, with credentials recorded as a length only."""
        self.journal.append(
            self.id, "wire",
            {"direction": event.direction.value,
             "bytes": len(event.payload),
             "redacted": event.redacted,
             "digest": None if event.redacted
                       else self.journal.put_blob(event.payload)},
            trace_id=self.trace_id, at=event.at, monotonic=event.monotonic)

    def __str__(self) -> str:
        state = "logged in" if self._logged_in else "not logged in"
        return f"<Session {self.id} {self.name} {state}>"
