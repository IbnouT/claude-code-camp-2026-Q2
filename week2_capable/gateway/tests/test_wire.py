"""Framing and capture. Hermetic: no game, no sockets except a fake one.

The central property is that framing must not depend on how the socket happened to split the
stream. Every test that feeds bytes whole is paired with one that feeds them one at a time,
because a filter that processes chunks independently passes the first and fails the second, and
the failure is invisible in the output: text still looks like text.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from mud_gateway.wire import (DO, DONT, IAC, PROMPT, SB, SE, WILL, WONT, Direction, Framer,
                          Transport, WireEvent, strip_ansi)

PROMPT_BYTES = b"\r\n24H 100M 82V (news) (motd) > "


def drip(framer: Framer, data: bytes) -> bytes:
    """Feed one byte at a time, the worst case a socket can produce."""
    out = bytearray()
    for index in range(len(data)):
        out += framer.feed(data[index:index + 1])
    return bytes(out)


class TestFramingIsIndependentOfChunkBoundaries:
    def test_plain_text_survives_either_way(self):
        data = b"The Bakery" + PROMPT_BYTES
        assert Framer().feed(data) == drip(Framer(), data)

    def test_a_negotiation_split_across_the_boundary_is_not_lost(self):
        # IAC WILL ECHO, then text. Fed whole this is easy. Fed one byte at a time, a
        # stateless filter emits the 255 and then the option byte as if they were text.
        data = bytes([IAC, WILL, 1]) + b"The Bakery"
        assert Framer().feed(data) == b"The Bakery"
        assert drip(Framer(), data) == b"The Bakery"

    def test_the_option_byte_arriving_in_the_next_chunk_is_held(self):
        framer = Framer()
        first = framer.feed(b"abc" + bytes([IAC, DO]))
        assert first == b"abc"
        assert framer.held == 2, "the incomplete sequence must be retained"
        second = framer.feed(bytes([1]) + b"def")
        assert second == b"def"
        assert framer.held == 0

    def test_a_subnegotiation_split_across_the_boundary_is_swallowed_whole(self):
        data = bytes([IAC, SB, 24, 0]) + b"xterm" + bytes([IAC, SE]) + b"visible"
        assert Framer().feed(data) == b"visible"
        assert drip(Framer(), data) == b"visible"

    def test_an_unterminated_subnegotiation_is_held_rather_than_leaking(self):
        framer = Framer()
        assert framer.feed(bytes([IAC, SB, 24]) + b"partial") == b""
        assert framer.held > 0
        assert framer.feed(bytes([IAC, SE]) + b"rest") == b"rest"

    def test_a_doubled_iac_is_one_literal_byte(self):
        data = bytes([IAC, IAC]) + b"tail"
        assert Framer().feed(data) == bytes([IAC]) + b"tail"
        assert drip(Framer(), data) == bytes([IAC]) + b"tail"

    def test_every_offered_option_is_refused_exactly_once(self):
        framer = Framer()
        framer.feed(bytes([IAC, WILL, 1, IAC, DO, 3]))
        assert framer.negotiations == [bytes([IAC, DONT, 1]), bytes([IAC, WONT, 3])]

    def test_refusals_are_identical_however_the_stream_is_split(self):
        whole, dripped = Framer(), Framer()
        whole.feed(bytes([IAC, WILL, 1, IAC, DO, 3]))
        drip(dripped, bytes([IAC, WILL, 1, IAC, DO, 3]))
        assert whole.negotiations == dripped.negotiations


class TestReplyCompletion:
    def test_the_vitals_prompt_completes_a_reply(self):
        framer = Framer()
        assert not framer.complete()
        framer.feed(b"You see nothing." + PROMPT_BYTES)
        assert framer.complete()

    def test_the_login_menu_does_not_count_as_a_prompt(self):
        # A bare "> " check would match this and enter the game loop on the menu screen.
        framer = Framer()
        framer.feed(b"1) Enter the game.\r\nMake your choice: ")
        assert not framer.complete()

    def test_a_prompt_split_across_chunks_is_still_detected(self):
        framer = Framer()
        framer.feed(b"text\r\n24H 100")
        assert not framer.complete()
        framer.feed(b"M 82V > ")
        assert framer.complete()

    def test_taking_a_reply_starts_the_next_one_clean(self):
        framer = Framer()
        framer.feed(b"first" + PROMPT_BYTES)
        assert b"first" in framer.take()
        assert not framer.complete()
        assert framer.take() == b""


class TestAnsi:
    def test_colour_is_removed_without_touching_the_text(self):
        assert strip_ansi(b"\x1b[0;33mThe Bakery\x1b[0m") == b"The Bakery"

    def test_colour_is_kept_in_the_frame_itself(self):
        # The parser needs the codes: they label titles, exits and objects. Stripping here
        # would throw away the server's own annotation.
        framer = Framer()
        assert b"\x1b[0;33m" in framer.feed(b"\x1b[0;33mThe Bakery\x1b[0m")


class FakeGame:
    """A server that answers over a real socket, so the transport is exercised for real."""

    def __init__(self, script: list[bytes], *, chunk: int | None = None) -> None:
        self.script, self.chunk = script, chunk
        self.received: list[bytes] = []
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        for message in self.script:
            if self.chunk:
                for start in range(0, len(message), self.chunk):
                    writer.write(message[start:start + self.chunk])
                    await writer.drain()
                    await asyncio.sleep(0.01)
            else:
                writer.write(message)
                await writer.drain()
            try:
                self.received.append(await asyncio.wait_for(reader.read(4096), timeout=2))
            except asyncio.TimeoutError:
                pass
        writer.close()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


class TestTransport:
    async def test_it_reads_a_reply_and_records_both_directions(self):
        game = FakeGame([b"The Bakery" + PROMPT_BYTES])
        await game.start()
        transport = Transport(port=game.port, timeout=5)
        await transport.connect()
        try:
            seen = await transport.read_until(PROMPT, quiet=0.3)
            assert b"The Bakery" in seen
            assert {event.direction for event in transport.events} == {Direction.IN}
            await transport.send("look")
            assert Direction.OUT in {event.direction for event in transport.events}
        finally:
            await transport.close()
            await game.stop()

    async def test_a_stream_split_into_single_bytes_yields_the_same_reply(self):
        # Framing must not depend on how the socket split the stream.
        payload = bytes([IAC, WILL, 1]) + b"The Bakery" + PROMPT_BYTES
        game = FakeGame([payload], chunk=1)
        await game.start()
        transport = Transport(port=game.port, timeout=8)
        await transport.connect()
        try:
            seen = await transport.read_until(PROMPT, quiet=0.4)
            assert b"The Bakery" in seen
            assert bytes([IAC]) not in seen
        finally:
            await transport.close()
            await game.stop()

    async def test_the_captured_bytes_reconstruct_what_the_server_sent(self):
        """Byte-exactness of the capture, over a stream deliberately split into threes.

        `read_until` stops the instant the prompt matches, which is mid-line, so the trailing
        "(news) (motd) > " is still in flight. The capture is therefore a byte-exact PREFIX at
        that moment, and draining the rest makes it byte-exact whole. An earlier version of
        this test compared against the full payload and failed on correct behaviour.
        """
        payload = b"chunk one" + PROMPT_BYTES
        game = FakeGame([payload], chunk=3)
        await game.start()
        transport = Transport(port=game.port, timeout=8)
        await transport.connect()
        try:
            await transport.read_until(PROMPT, quiet=0.4)
            captured = b"".join(e.payload for e in transport.events
                                if e.direction is Direction.IN)
            assert payload.startswith(captured), "the capture must be an exact prefix"
            await transport.drain_pending(window=0.4)
            captured = b"".join(e.payload for e in transport.events
                                if e.direction is Direction.IN)
            assert captured == payload, "the wire log must be byte-exact"
        finally:
            await transport.close()
            await game.stop()

    async def test_a_secret_line_records_its_length_and_not_its_content(self):
        game = FakeGame([b"Password: "])
        await game.start()
        transport = Transport(port=game.port, timeout=5)
        await transport.connect()
        try:
            await transport.send("hunter2", secret=True)
            outbound = [e for e in transport.events if e.direction is Direction.OUT]
            assert outbound[-1].redacted
            assert b"hunter2" not in outbound[-1].payload
            assert len(outbound[-1].payload) == len("hunter2\n")
            # And the whole log must be clean, not just that one event.
            assert all(b"hunter2" not in e.payload for e in transport.events)
        finally:
            await transport.close()
            await game.stop()

    async def test_using_a_closed_transport_raises_rather_than_doing_nothing(self):
        from mud_gateway.wire import NotConnected
        transport = Transport(port=1, timeout=1)
        with pytest.raises(NotConnected):
            await transport.send("look")

    async def test_a_wire_callback_sees_every_event_as_it_happens(self):
        seen: list[WireEvent] = []
        game = FakeGame([b"hello" + PROMPT_BYTES])
        await game.start()
        transport = Transport(port=game.port, timeout=5, on_wire=seen.append)
        await transport.connect()
        try:
            await transport.read_until(PROMPT, quiet=0.3)
            assert seen
            assert all(isinstance(event, WireEvent) for event in seen)
        finally:
            await transport.close()
            await game.stop()
