"""Bytes to and from the game, captured exactly, with negotiation filtered out.

The lowest layer. It knows about sockets, telnet control codes, and where one reply ends. It
knows nothing about rooms, commands or consumers, so it can be tested against a fake server
with no game running and replayed against recorded traffic with no server at all.

INCREMENTAL FRAMING IS THE POINT OF THIS MODULE. A socket hands over arbitrary chunks, so a
three-byte IAC sequence or the vitals prompt can be split across two reads. A filter that
processes each chunk independently loses the tail of whatever straddles the boundary, and the
loss is invisible: the text still looks like text. So parsing runs over a persistent buffer and
an incomplete sequence at the end of a chunk is held, not dropped.

WHAT GETS CAPTURED, AND WHAT DOES NOT. Every byte in both directions is recorded with a
monotonic and a wall timestamp, because a claim about a run that cannot be traced to the bytes
that caused it is an assertion. The one exception is credentials: the password line is recorded
as its length, never its content, since a wire log is read by people and shipped to a viewer.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from enum import Enum

#: Telnet control bytes, and only the ones the game actually sends.
IAC = 255
DONT, DO, WONT, WILL = 254, 253, 252, 251
SB, SE = 250, 240

#: The reply delimiter. tbaMUD ends every command response with a prompt carrying vitals, so
#: the shape is stable while the digits vary. Measured on 766 of 772 recorded tool results.
#: Matching a bare "> " instead would also match the login menu.
PROMPT = re.compile(rb"\d+H\s+\d+M\s+\d+V")

ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


class Direction(str, Enum):
    IN = "in"
    OUT = "out"


@dataclass(frozen=True)
class WireEvent:
    """One chunk of traffic, exactly as it crossed the socket.

    ``redacted`` marks a payload whose content was withheld. The length is still recorded,
    because "a 9 byte line was sent here" is what makes the sequence readable without
    disclosing the secret.
    """

    at: float
    monotonic: float
    direction: Direction
    payload: bytes
    redacted: bool = False

    def __str__(self) -> str:
        if self.redacted:
            return f"<WireEvent {self.direction.value} redacted bytes={len(self.payload)}>"
        preview = ANSI.sub(b"", self.payload)[:40].decode("latin-1").replace("\r", "")
        return (f"<WireEvent {self.direction.value} bytes={len(self.payload)} "
                f"text={preview!r}>")


class Framer:
    """Accumulates bytes, strips negotiation, and answers whether a reply is complete.

    Stateful on purpose. The whole reason this is a class rather than a function is that a
    control sequence split across two reads has to survive the boundary.
    """

    def __init__(self) -> None:
        self._pending = bytearray()   # bytes held because a sequence is incomplete
        self._text = bytearray()      # negotiation-free content collected so far
        self.replies: bytearray = bytearray()
        self.negotiations: list[bytes] = []

    def feed(self, chunk: bytes) -> bytes:
        """Add a chunk, return the negotiation-free bytes it contributed.

        Any reply this owes the server (a refusal for each offered option) accumulates in
        ``negotiations`` for the caller to send, rather than being written from here. A framer
        that owned a socket could not be tested without one.
        """
        self._pending += chunk
        produced = bytearray()
        index = 0
        data = self._pending
        while index < len(data):
            byte = data[index]
            if byte != IAC:
                produced.append(byte)
                index += 1
                continue
            # From here on the sequence may be incomplete, in which case we stop and keep it.
            if index + 1 >= len(data):
                break
            command = data[index + 1]
            if command in (DO, DONT, WILL, WONT):
                if index + 2 >= len(data):
                    break
                option = data[index + 2]
                # Refuse everything. This layer wants a plain byte stream, not MXP or MSDP.
                refusal = WONT if command in (DO, DONT) else DONT
                self.negotiations.append(bytes([IAC, refusal, option]))
                index += 3
            elif command == SB:
                end = data.find(bytes([IAC, SE]), index)
                if end == -1:
                    break
                index = end + 2
            elif command == IAC:
                produced.append(IAC)
                index += 2
            else:
                index += 2
        del data[:index]
        self._text += produced
        self.replies += produced
        return bytes(produced)

    @property
    def held(self) -> int:
        """Bytes retained because a control sequence straddles a chunk boundary."""
        return len(self._pending)

    def complete(self) -> bool:
        """Whether the collected content reaches a prompt."""
        return bool(PROMPT.search(self.replies))

    def take(self) -> bytes:
        """Return the collected reply and start a new one."""
        reply = bytes(self.replies)
        self.replies = bytearray()
        return reply

    def __str__(self) -> str:
        return (f"<Framer collected={len(self.replies)} held={self.held} "
                f"negotiations={len(self.negotiations)}>")


def strip_ansi(data: bytes) -> bytes:
    return ANSI.sub(b"", data)


class TransportError(Exception):
    pass


class NotConnected(TransportError):
    pass


class Transport:
    """An asyncio connection to the game, with every byte recorded.

    Async from the first line because this process also serves SSE and may hold more than one
    session, and a synchronous transport would have to be replaced to do either.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4000,
                 timeout: float = 20.0,
                 on_wire=None) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._framer = Framer()
        self._on_wire = on_wire
        self.events: list[WireEvent] = []

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = self._writer = None

    @property
    def closed(self) -> bool:
        return self._writer is None

    # -- traffic ------------------------------------------------------------

    async def send(self, line: str, *, secret: bool = False) -> None:
        """Write one line. ``secret`` records the length and withholds the content."""
        if self._writer is None:
            raise NotConnected("transport is closed")
        payload = (line + "\n").encode("latin-1")
        self._record(Direction.OUT, payload, redacted=secret)
        self._writer.write(payload)
        await self._writer.drain()

    async def read_until(self, pattern: re.Pattern[bytes], *, quiet: float | None,
                         deadline: float | None = None) -> bytes:
        """Read until the pattern appears, or until the server goes quiet.

        ``quiet=None`` means the pattern is required and silence is not an answer. The login
        sequence needs that: the server opens with a client-detection notice and then pauses,
        so a quiet-based read returns a partial banner and reports no prompt.
        """
        if self._reader is None:
            raise NotConnected("transport is closed")
        collected = bytearray()
        limit = time.monotonic() + (deadline or self.timeout)
        while time.monotonic() < limit:
            window = min(quiet or 1.0, max(0.05, limit - time.monotonic()))
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=window)
            except asyncio.TimeoutError:
                if quiet is not None and collected:
                    break
                continue
            if not chunk:
                break
            self._record(Direction.IN, chunk)
            collected += self._framer.feed(chunk)
            await self._answer_negotiations()
            if pattern.search(collected):
                break
        return bytes(collected)

    async def drain_pending(self, window: float = 0.15) -> bytes:
        """Take whatever is already waiting, without sending anything.

        Unsolicited output ends in a prompt like anything else, so left in the buffer it
        satisfies the next read and every reply arrives shifted by one. Kept rather than
        discarded, because the world acting on its own is a fact worth recording.
        """
        if self._reader is None:
            raise NotConnected("transport is closed")
        collected = bytearray()
        while True:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=window)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            self._record(Direction.IN, chunk)
            collected += self._framer.feed(chunk)
            await self._answer_negotiations()
        return bytes(collected)

    # -- internals ----------------------------------------------------------

    async def _answer_negotiations(self) -> None:
        while self._framer.negotiations:
            reply = self._framer.negotiations.pop(0)
            if self._writer is None:
                return
            self._record(Direction.OUT, reply)
            self._writer.write(reply)
            await self._writer.drain()

    def _record(self, direction: Direction, payload: bytes, *,
                redacted: bool = False) -> None:
        stored = (b"\x00" * len(payload)) if redacted else payload
        event = WireEvent(at=time.time(), monotonic=time.monotonic(),
                          direction=direction, payload=stored, redacted=redacted)
        self.events.append(event)
        if self._on_wire is not None:
            self._on_wire(event)

    def __str__(self) -> str:
        state = "closed" if self.closed else "open"
        return (f"<Transport {self.host}:{self.port} {state} "
                f"events={len(self.events)} {self._framer}>")
