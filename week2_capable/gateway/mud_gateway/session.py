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
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from .journal import Journal
from .knowledge_projection import KnowledgeProjector
from .observation_pipeline import ObservationPipeline
from .observe import Observation, WireReference
from .position import PositionObservation
from .wire import PROMPT, NotConnected, Transport, WireEvent, strip_ansi

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


class ReconnectFailed(NotConnected):
    """A dead game connection could not be restored before a command."""


class SessionPaused(RuntimeError):
    """A control operation owns the next command boundary."""


class SessionQuarantined(RuntimeError):
    """A partial reset prevents further mortal commands."""


@dataclass
class Reply:
    """One command and the bytes it produced, plus anything that arrived unbidden first."""

    command: str
    raw: bytes
    unsolicited: bytes
    complete: bool
    seq: int
    wire_ref: WireReference | None = None
    observations: tuple[Observation, ...] = ()
    position: PositionObservation | None = None

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
                 session_id: str | None = None,
                 knowledge: KnowledgeProjector | None = None) -> None:
        self.id = session_id or f"{name}-{uuid.uuid4().hex[:8]}"
        self.name = name
        self._password = password
        self.journal = journal
        self.transport = Transport(host=host, port=port, timeout=timeout,
                                  on_wire=self._journal_wire)
        self._logged_in = False
        self._command_lock = asyncio.Lock()
        self._control_state = "running"
        self.trace_id: str | None = None
        self.observations = ObservationPipeline(
            journal,
            self.id,
            knowledge=knowledge,
        )

    # -- lifecycle ----------------------------------------------------------

    async def open(self) -> None:
        """Connect and walk the whole entry sequence."""
        self._logged_in = False
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
        return self._logged_in and not self.transport.closed

    @property
    def control_state(self) -> str:
        return self._control_state

    # -- commands -----------------------------------------------------------

    async def command(self, line: str, *, trace_id: str | None = None) -> Reply:
        """Send one line and collect its reply, with the window aligned first."""
        self._assert_commands_allowed()
        async with self._command_lock:
            self._assert_commands_allowed()
            return await self._command_unlocked(line, trace_id=trace_id)

    async def poll(self, *, trace_id: str | None = None) -> Reply:
        """Return unsolicited output without sending a game command."""
        self._assert_commands_allowed()
        async with self._command_lock:
            self._assert_commands_allowed()
            trace = trace_id or self.trace_id
            async with self._capture_trace(trace):
                source_after = self.journal.last_seq(self.id)
                pending = await self.transport.drain_pending()
                event = self.journal.append(
                    self.id,
                    "poll",
                    {
                        "bytes": len(pending),
                        "text": strip_ansi(pending).decode("latin-1"),
                    },
                    trace_id=trace,
                )
                wire_ref = self._wire_reference(source_after, event.seq, pending)
                observations, position = self.observations.ingest(
                    pending,
                    wire_ref,
                    trace_id=trace,
                )
                return Reply(
                    command="poll",
                    raw=pending,
                    unsolicited=b"",
                    complete=True,
                    seq=event.seq,
                    wire_ref=wire_ref,
                    observations=observations,
                    position=position,
                )

    @asynccontextmanager
    async def pause(self, *, timeout: float) -> AsyncIterator[None]:
        """Own the next safe command boundary for one control operation."""
        if self._control_state == "quarantined":
            raise SessionQuarantined(
                "session is quarantined, only an explicit reset retry or stop is allowed"
            )
        try:
            await asyncio.wait_for(self._command_lock.acquire(), timeout=timeout)
        except TimeoutError as error:
            raise SessionPaused(
                "timed out waiting for the current mortal command to finish"
            ) from error
        self._control_state = "paused"
        self.journal.append(self.id, "control_state", {"state": "paused"})
        try:
            yield
        finally:
            if self._control_state == "paused":
                self._control_state = "running"
                self.journal.append(self.id, "control_state", {"state": "running"})
            self._command_lock.release()

    def quarantine(self, reason: str) -> None:
        """Fail closed after game mutation whose final state is unverified."""
        self._control_state = "quarantined"
        self.journal.append(
            self.id,
            "control_state",
            {"state": "quarantined", "reason": reason},
        )

    def allow_reset_retry(self) -> None:
        """Allow only the reset coordinator to retry a quarantined session."""
        if self._control_state != "quarantined":
            raise RuntimeError("reset retry requires a quarantined session")
        self._control_state = "running"

    async def reset_command(self, line: str) -> Reply:
        """Run a verification command while the reset coordinator owns the lock."""
        if not self._command_lock.locked():
            raise RuntimeError("reset command requires the paused command boundary")
        return await self._command_unlocked(line)

    async def reconnect_for_reset(self) -> None:
        """Reconnect the selected character without opening a second mortal session."""
        if not self._command_lock.locked():
            raise RuntimeError("reset reconnect requires the paused command boundary")
        await self._reconnect("verified_reset")

    # -- internals ----------------------------------------------------------

    def _assert_commands_allowed(self) -> None:
        if self._control_state == "paused":
            raise SessionPaused("session is paused for a control operation")
        if self._control_state == "quarantined":
            raise SessionQuarantined(
                "session is quarantined after an incomplete reset"
            )

    async def _command_unlocked(
        self,
        line: str,
        *,
        trace_id: str | None = None,
    ) -> Reply:
        trace = trace_id or self.trace_id
        async with self._capture_trace(trace):
            return await self._captured_command(line, trace)

    async def _captured_command(
        self,
        line: str,
        trace: str | None,
    ) -> Reply:
        source_after = self.journal.last_seq(self.id)
        pending = b""
        reconnect_required = False
        try:
            pending = await self.transport.drain_pending()
        except NotConnected:
            reconnect_required = True
        if pending:
            unsolicited = self.journal.append(
                self.id,
                "unsolicited",
                {
                    "bytes": len(pending),
                    "text": strip_ansi(pending).decode("latin-1"),
                },
                trace_id=trace,
            )
            pending_ref = self._wire_reference(
                source_after,
                unsolicited.seq,
                pending,
            )
            self.observations.ingest(
                pending,
                pending_ref,
                trace_id=trace,
            )
            source_after = self.journal.last_seq(self.id)
        if reconnect_required or self.transport.closed:
            await self._reconnect("connection_lost_before_command")
            source_after = self.journal.last_seq(self.id)
        await self.transport.send(line)
        raw = await self.transport.read_until(PROMPT, quiet=0.6)
        event = self.journal.append(
            self.id,
            "command",
            {
                "line": line,
                "reply_bytes": len(raw),
                "complete": bool(PROMPT.search(raw)),
                "unsolicited_bytes": len(pending),
            },
            trace_id=trace,
        )
        wire_ref = self._wire_reference(source_after, event.seq, raw)
        attempted_move = line.casefold() if line.casefold() in {
            "north", "south", "east", "west", "up", "down",
            "n", "s", "e", "w", "u", "d",
        } else None
        observations, position = self.observations.ingest(
            raw,
            wire_ref,
            attempted_move=attempted_move,
            trace_id=trace,
        )
        return Reply(
            command=line,
            raw=raw,
            unsolicited=pending,
            complete=bool(PROMPT.search(raw)),
            seq=event.seq,
            wire_ref=wire_ref,
            observations=observations,
            position=position,
        )

    async def _reconnect(self, reason: str) -> None:
        """Restore a dead connection only before the next command is sent."""
        self._logged_in = False
        self.journal.append(
            self.id,
            "session_reconnect",
            {"character": self.name, "reason": reason},
        )
        try:
            await self.transport.close()
            await self.open()
        except (LoginFailed, NotConnected, OSError, TimeoutError) as error:
            self._logged_in = False
            try:
                await self.transport.close()
            except (ConnectionError, OSError):
                pass
            self.journal.append(
                self.id,
                "session_reconnect_failed",
                {
                    "character": self.name,
                    "reason": reason,
                    "error": type(error).__name__,
                },
            )
            raise ReconnectFailed(
                f"could not reconnect {self.name!r} to the game: {error}"
            ) from error

    @asynccontextmanager
    async def _capture_trace(
        self,
        trace: str | None,
    ) -> AsyncIterator[None]:
        """Attach one capability trace to every wire callback in its window."""
        previous = self.trace_id
        self.trace_id = trace
        try:
            yield
        finally:
            self.trace_id = previous

    def _journal_wire(self, event: WireEvent) -> None:
        """Every byte, both directions, with credentials recorded as a length only."""
        wire = self.journal.append(
            self.id, "wire",
            {"direction": event.direction.value,
             "bytes": len(event.payload),
             "redacted": event.redacted,
             "digest": None if event.redacted
                       else self.journal.put_blob(event.payload)},
            trace_id=self.trace_id, at=event.at, monotonic=event.monotonic)
        self.journal.append(
            self.id,
            "wire_text",
            {
                "direction": event.direction.value,
                "wire_seq": wire.seq,
                "bytes": len(event.payload),
                "redacted": event.redacted,
                "encoding": "latin-1",
                "ansi": "preserved",
                "text": (
                    None
                    if event.redacted
                    else event.payload.decode("latin-1")
                ),
            },
            trace_id=self.trace_id,
            at=event.at,
            monotonic=event.monotonic,
        )

    def _wire_reference(
        self, after: int, fallback_seq: int, raw: bytes
    ) -> WireReference:
        inbound = [
            event for event in self.journal.since(self.id, after)
            if event.kind == "wire" and event.payload.get("direction") == "in"
        ]
        first = inbound[0].seq if inbound else fallback_seq
        last = inbound[-1].seq if inbound else fallback_seq
        return WireReference.from_bytes(self.id, first, last, raw)

    def __str__(self) -> str:
        state = "logged in" if self.logged_in else "not logged in"
        return f"<Session {self.id} {self.name} {state}>"
