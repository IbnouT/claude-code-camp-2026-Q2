"""The audited fallback is supported, denied by default, and profile-gated."""

from __future__ import annotations

import json

import pytest

from mud_gateway import commands
from mud_gateway.journal import Journal
from mud_gateway.profiles import PermissionDenied, Surface, load_profile
from mud_gateway.raw import MAX_LINE, NotPermitted, Role, check, send_raw
from mud_gateway.session import Reply


class ScriptedSession:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.id = "s1"
        self.lines: list[str] = []

    async def command(self, line: str, **_kwargs) -> Reply:
        self.lines.append(line)
        return Reply(command=line, raw=b"Ok.\r\n", unsolicited=b"", complete=True, seq=1)


@pytest.fixture()
def journal(tmp_path):
    j = Journal(tmp_path / "j.db")
    yield j
    j.close()


class TestItIsDeniedByDefault:
    """Supporting raw does not advertise or authorize it by default."""

    def test_default_profile_does_not_offer_it(self):
        surface = Surface(load_profile("direct-full"))
        assert "send_raw" not in json.dumps(surface.schemas())

    def test_default_profile_refuses_a_direct_call(self):
        surface = Surface(load_profile("direct-full"))
        with pytest.raises(PermissionDenied):
            surface.resolve(
                "send_raw",
                {"line": "look", "reason": "capability gap"},
            )

    def test_explicit_profile_advertises_and_authorizes_it(self):
        surface = Surface(load_profile("direct-full", allow=["send_raw"]))
        assert [schema["name"] for schema in surface.schemas()] == ["send_raw"]
        invocation = surface.resolve(
            "send_raw",
            {"line": "look", "reason": "capability gap"},
        )
        assert invocation.capability is commands.BY_NAME["send_raw"]

    def test_the_caller_cannot_claim_a_trusted_role(self):
        with pytest.raises(NotPermitted):
            check("goto 3001", "harness", reason="pretending")
        with pytest.raises(NotPermitted):
            check("goto 3001", True, reason="pretending")
        with pytest.raises(NotPermitted):
            check("goto 3001", None, reason="no role at all")


class TestWhatEvenTheHarnessMayNotSend:
    """Refused for every role, because the reason has nothing to do with trust."""

    def test_a_newline_is_refused_so_one_call_stays_one_command(self):
        # Otherwise a logged line becomes an unlogged batch and the journal is a lie.
        with pytest.raises(ValueError, match="newline"):
            check("look\r\nquit", Role.HARNESS, reason="debug")

    def test_a_null_byte_is_refused_too(self):
        with pytest.raises(ValueError):
            check("look\x00quit", Role.HARNESS, reason="debug")

    def test_an_empty_line_is_refused_because_it_is_a_menu_answer(self):
        with pytest.raises(ValueError, match="bare return"):
            check("   ", Role.HARNESS, reason="debug")

    def test_a_line_the_server_would_truncate_is_refused(self):
        # A truncated line means the journal records something the game never ran.
        with pytest.raises(ValueError, match=str(MAX_LINE)):
            check("x" * (MAX_LINE + 1), Role.HARNESS, reason="debug")

    def test_a_send_with_no_reason_is_refused(self):
        # It is the only record of why, since by definition no command definition explains it.
        with pytest.raises(ValueError, match="reason"):
            check("look", Role.HARNESS, reason="")


class TestWhatTheHarnessMaySend:
    def test_a_valid_line_passes_with_its_role_and_reason(self):
        validated = check("goto 3030", Role.HARNESS, reason="recording the door fixture")
        assert validated.line == "goto 3030"
        assert validated.role is Role.HARNESS
        assert validated.reason == "recording the door fixture"

    async def test_it_is_journalled_before_it_is_sent(self, journal):
        # A line that crashes the connection must still be in the record. Journalling on
        # success only would hide exactly the case anyone would go looking for.
        session = ScriptedSession(journal)
        await send_raw(session, "goto 3030", role=Role.OPERATOR, reason="debugging a hang")
        events = journal.since("s1", kind="capability_gap")
        assert len(events) == 1
        assert events[0].payload["line"] == "goto 3030"
        assert events[0].payload["role"] == "operator"
        assert events[0].payload["reason"] == "debugging a hang"

    async def test_a_refused_send_never_reaches_the_game(self, journal):
        session = ScriptedSession(journal)
        with pytest.raises(NotPermitted):
            await send_raw(session, "goto 3030", role="agent", reason="please")
        assert session.lines == []
        assert journal.since("s1", kind="capability_gap") == []
