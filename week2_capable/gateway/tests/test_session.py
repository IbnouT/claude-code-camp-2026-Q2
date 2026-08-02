"""Login and command framing, which had no tests while everything else depended on them.

Every module in this package receives its input through `Session.command`, and the four-step
entry sequence is the one piece of the gateway that cannot be exercised by replaying a
recording: a recording starts after login succeeded.

The transport is scripted rather than mocked loosely. Each test states the bytes the server
sends and then asserts on what the session did with them, so a change in the entry sequence
fails here rather than against a live game at the cost of a connection.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from mud_gateway.journal import Journal
from mud_gateway.session import (ENTER_GAME, LoginFailed, Reply, Session)
from mud_gateway.wire import Direction, WireEvent

GREETING = b"\r\nBy what name do you wish to be known? "
PASSWORD = b"\r\nPassword: "
MOTD = b"\r\n*** PRESS RETURN: "
MENU = b"\r\nMake your choice: "
PROMPT_BYTES = b"\r\n100H 82M 96V > "


class ScriptedTransport:
    """Hands back a prepared reply for each `read_until`, and records what was sent."""

    def __init__(self, script: list[bytes]) -> None:
        self.script = list(script)
        self.sent: list[tuple[str, bool]] = []
        self.pending: list[bytes] = []
        self.host, self.port, self.timeout = "test", 0, 1.0
        self.closed = False
        self.connected = False
        self.in_flight = 0
        self.max_in_flight = 0

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def send(self, line: str, *, secret: bool = False) -> None:
        self.sent.append((line, secret))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)

    async def read_until(self, pattern: re.Pattern[bytes], *, quiet, deadline=None) -> bytes:
        await asyncio.sleep(0)
        self.in_flight = max(0, self.in_flight - 1)
        return self.script.pop(0) if self.script else b""

    async def drain_pending(self, window: float = 0.15) -> bytes:
        return self.pending.pop(0) if self.pending else b""


@pytest.fixture()
def journal(tmp_path):
    j = Journal(tmp_path / "j.db")
    yield j
    j.close()


def make(journal, script, **kwargs):
    session = Session(journal, name="poucet", password="secret", **kwargs)
    session.transport = ScriptedTransport(script)
    return session


class TestTheEntrySequence:
    """Four steps, and the game acknowledges three of them with a different prompt."""

    async def test_a_clean_login_walks_name_password_motd_and_menu(self, journal):
        session = make(journal, [GREETING, PASSWORD, MOTD, MENU, PROMPT_BYTES])
        await session.open()
        assert session.logged_in
        # Empty line to clear the MOTD, then "1" to enter the game from the menu.
        assert [line for line, _ in session.transport.sent] == ["poucet", "secret", "",
                                                               ENTER_GAME]

    async def test_the_password_is_sent_marked_secret(self, journal):
        # The transport redacts on this flag. Sending it unmarked would put the password in
        # the wire journal in plain text, where it would stay.
        session = make(journal, [GREETING, PASSWORD, MOTD, MENU, PROMPT_BYTES])
        await session.open()
        assert ("secret", True) in session.transport.sent
        assert ("poucet", False) in session.transport.sent

    def test_a_redacted_password_never_reaches_persisted_evidence(
            self, journal, tmp_path):
        session = Session(
            journal, name="poucet", password="do-not-persist",
            session_id="credential-test")
        session._journal_wire(WireEvent(
            at=1.0, monotonic=2.0, direction=Direction.OUT,
            payload=b"\x00" * len("do-not-persist\n"), redacted=True))

        exported = tmp_path / "credential-test.jsonl"
        journal.export_jsonl(session.id, exported)
        evidence = exported.read_bytes() + journal.path.read_bytes()
        assert b"do-not-persist" not in evidence
        decoded = journal.since(session.id, kind="wire_text")
        assert decoded[0].payload["redacted"] is True
        assert decoded[0].payload["text"] is None

    async def test_arriving_straight_at_a_prompt_needs_no_further_steps(self, journal):
        # A reconnect can land in the game directly. Sending a menu choice then would type a
        # stray "1" into the world.
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        assert session.logged_in
        assert ENTER_GAME not in [line for line, _ in session.transport.sent]

    async def test_a_wrong_password_raises_rather_than_looping(self, journal):
        session = make(journal, [GREETING, PASSWORD, b"\r\nWrong password.\r\n"])
        with pytest.raises(LoginFailed, match="rejected"):
            await session.open()
        assert not session.logged_in

    async def test_a_server_that_never_prompts_gives_up_instead_of_hanging(self, journal):
        # Six steps of nothing, then a stated failure. An unbounded loop here would hold a
        # connection open forever against a server that is not going to answer.
        session = make(journal, [GREETING, PASSWORD] + [b"\r\nnothing\r\n"] * 12)
        with pytest.raises(LoginFailed, match="no prompt"):
            await session.open()

    async def test_a_failed_login_is_journalled_with_its_reason(self, journal):
        session = make(journal, [GREETING, PASSWORD, b"\r\nWrong password.\r\n"])
        with pytest.raises(LoginFailed):
            await session.open()
        kinds = [event.kind for event in journal.since(session.id)]
        assert "login_failed" in kinds
        assert "login" not in kinds


class TestCommands:
    async def test_a_command_returns_its_reply_and_the_journal_sequence(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [b"The Temple Of Midgaard\r\n" + PROMPT_BYTES]
        reply = await session.command("look")
        assert "The Temple Of Midgaard" in reply.text
        assert reply.complete
        assert reply.seq > 0
        assert reply.wire_ref is not None
        assert reply.observations
        assert reply.position is not None

    async def test_a_reply_with_no_prompt_is_marked_incomplete_rather_than_trusted(self,
                                                                                   journal):
        # The prompt is the delimiter. Without it the reply may be half a room, and a parser
        # told it was complete would report the missing half as absent.
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [b"You are getting hungry.\r\n"]
        assert not (await session.command("look")).complete

    async def test_output_that_arrived_unbidden_is_kept_and_not_read_as_the_reply(self,
                                                                                  journal):
        # A mob walking in between commands would otherwise be returned as the answer to
        # whatever was typed next.
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.pending = [b"A large dog leaves north.\r\n"]
        session.transport.script = [b"The Temple Of Midgaard\r\n" + PROMPT_BYTES]
        reply = await session.command("look")
        assert b"large dog" in reply.unsolicited
        assert "large dog" not in reply.text

    async def test_unsolicited_output_is_journalled_so_it_is_not_simply_lost(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.pending = [b"A large dog leaves north.\r\n"]
        session.transport.script = [PROMPT_BYTES]
        await session.command("look")
        assert any(event.kind == "unsolicited" for event in journal.since(session.id))

    async def test_unsolicited_combat_and_vitals_are_projected_before_next_command(
        self,
        journal,
    ):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.pending = [
            b"The rabbit hits you hard.\r\n29H 82M 95V > "
        ]
        session.transport.script = [PROMPT_BYTES]

        await session.command("look")

        observations = [
            event.payload
            for event in journal.since(session.id, kind="observation")
        ]
        assert any(
            observation.get("kind") == "combat"
            and observation.get("text") == "The rabbit hits you hard."
            for observation in observations
        )
        assert any(
            observation.get("kind") == "vitals"
            and observation.get("hit") == 29
            and observation.get("mana") == 82
            and observation.get("move") == 95
            for observation in observations
        )

    async def test_a_trace_id_travels_from_the_session_onto_the_command(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.trace_id = "route-7"
        session.transport.script = [PROMPT_BYTES]
        await session.command("north")
        commands = journal.since(session.id, kind="command")
        assert commands[-1].trace_id == "route-7"

    async def test_explicit_command_trace_owns_every_wire_frame(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        original_send = session.transport.send
        original_read = session.transport.read_until

        async def send(line: str, *, secret: bool = False) -> None:
            session._journal_wire(WireEvent(
                at=10,
                monotonic=10,
                direction=Direction.OUT,
                payload=(line + "\n").encode(),
                redacted=secret,
            ))
            await original_send(line, secret=secret)

        async def read(pattern, *, quiet, deadline=None):
            data = await original_read(pattern, quiet=quiet, deadline=deadline)
            session._journal_wire(WireEvent(
                at=11,
                monotonic=11,
                direction=Direction.IN,
                payload=data,
            ))
            return data

        session.transport.send = send
        session.transport.read_until = read
        session.transport.script = [PROMPT_BYTES]

        await session.command("north", trace_id="capability-42")

        wire = journal.since(session.id, kind="wire")
        assert len(wire) == 2
        assert {event.trace_id for event in wire} == {"capability-42"}
        decoded = journal.since(session.id, kind="wire_text")
        assert len(decoded) == 2
        assert {event.trace_id for event in decoded} == {"capability-42"}
        assert decoded[0].payload["text"] == "north\n"
        assert decoded[1].payload["text"] == PROMPT_BYTES.decode("latin-1")
        assert session.trace_id is None

    async def test_parsed_facts_and_metrics_are_committed(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [
            b"\x1b[0;33mThe Temple\x1b[0m\r\n"
            b"\x1b[0;36m[ Exits: n ]\x1b[0m\r\n" + PROMPT_BYTES
        ]
        await session.command("look")
        kinds = [event.kind for event in journal.since(session.id)]
        assert "parser_input" in kinds
        assert "observation" in kinds
        assert "position" in kinds
        assert "parse_metric" in kinds
        parser_input = journal.since(session.id, kind="parser_input")[-1]
        assert parser_input.payload["text"] == (
            "The Temple\n[ Exits: n ]\n100H 82M 96V >"
        )
        assert parser_input.payload["wire_ref"]["digest"]

    async def test_unknown_output_is_an_event_not_silent_loss(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [b"Something entirely novel.\r\n" + PROMPT_BYTES]
        await session.command("look")
        unknown = journal.since(session.id, kind="unparsed")
        assert unknown
        assert unknown[0].payload["text"] == "Something entirely novel."

    async def test_concurrent_callers_are_serialized(self, journal):
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [PROMPT_BYTES, PROMPT_BYTES]
        session.transport.in_flight = 0
        session.transport.max_in_flight = 0

        first, second = await asyncio.gather(
            session.command("look"),
            session.command("score"),
        )

        commands = journal.since(session.id, kind="command")
        assert [event.payload["line"] for event in commands] == ["look", "score"]
        assert first.seq < second.seq
        assert session.transport.max_in_flight == 1


class TestClosing:
    async def test_closing_a_live_session_quits_the_game_first(self, journal):
        # Dropping the socket leaves the character linkdead in the world, which changes the
        # state the next run starts from.
        session = make(journal, [GREETING, PASSWORD, PROMPT_BYTES])
        await session.open()
        session.transport.script = [PROMPT_BYTES]
        await session.close()
        assert ("quit", False) in session.transport.sent
        assert session.transport.closed
        assert not session.logged_in

    async def test_closing_a_session_that_never_logged_in_sends_nothing(self, journal):
        session = make(journal, [])
        await session.close()
        assert session.transport.sent == []
        assert session.transport.closed


class TestTheReplyItself:
    def test_the_text_drops_ansi_and_carriage_returns(self):
        reply = Reply(command="look", raw=b"\x1b[33mThe Temple\x1b[0m\r\nhere",
                      unsolicited=b"", complete=True, seq=1)
        assert reply.text == "The Temple\nhere"

    def test_the_labeled_form_previews_the_text_without_dumping_it(self):
        reply = Reply(command="look", raw=b"x" * 400, unsolicited=b"y", complete=False, seq=1)
        line = str(reply)
        assert line.startswith("<Reply 'look' bytes=400 complete=False unsolicited=1")
        assert len(line) < 140
