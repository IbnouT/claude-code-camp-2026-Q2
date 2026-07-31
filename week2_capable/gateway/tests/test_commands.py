"""Capability definitions, command rendering, and typed execution."""

from __future__ import annotations

import ast
import pathlib

import pytest

from mud_gateway.commands import AVAILABLE, BY_NAME, IMMORTAL, build
from mud_gateway.journal import Journal
from mud_gateway.mcp_server import execute, failure, seed_login_observations
from mud_gateway.profiles import PermissionDenied, Surface, load_profile
from mud_gateway.results import CommandFailure, CommandObservation
from mud_gateway.session import Reply

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "mud_gateway"


class TestRegistry:
    def test_every_supported_family_is_present(self):
        assert {capability.family for capability in AVAILABLE} >= {
            "combat",
            "commerce",
            "fallback",
            "items",
            "lifecycle",
            "magic",
            "movement",
            "perception",
            "position",
            "self",
            "social",
            "status",
            "tracking",
            "training",
        }

    def test_required_arguments_and_enums_reach_the_schema(self):
        attack = BY_NAME["attack"].schema()["inputSchema"]
        assert attack["required"] == ["target"]
        assert attack["properties"]["style"]["enum"] == ["hit", "murder", "kill"]
        assert attack["properties"]["style"]["default"] == "kill"

    def test_unknown_arguments_are_rejected(self):
        with pytest.raises(ValueError, match="unknown arguments"):
            BY_NAME["look"].validate({"surprise": "value"})

    def test_future_capabilities_are_defined_but_unavailable(self):
        assert not BY_NAME["observe"].available
        assert not BY_NAME["navigate"].available

    def test_registry_has_no_immortal_command_name(self):
        assert not {capability.name for capability in AVAILABLE} & IMMORTAL

    def test_the_mortal_package_does_not_import_an_admin_surface(self):
        offenders = []
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name in ("admin.py", "fixtures.py"):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (
                        node.module or "").endswith("admin"):
                    offenders.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.endswith("admin"):
                            offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == []


class TestRendering:
    @pytest.mark.parametrize(
        ("name", "arguments", "line"),
        [
            ("move", {"direction": "north"}, "north"),
            ("look", {}, "look"),
            ("look", {"target": "chest", "preposition": "in"}, "look in chest"),
            ("check", {"kind": "exits"}, "exits"),
            ("set_position", {"position": "rest"}, "rest"),
            ("track", {"target": "rat"}, "track rat"),
            ("attack", {"target": "rat"}, "kill rat"),
            (
                "skill_strike",
                {"skill": "kick", "target": "rat"},
                "kick rat",
            ),
            (
                "get_item",
                {"item": "bread", "count": 2, "container": "bag"},
                "get 2 bread bag",
            ),
            (
                "equip_item",
                {"action": "wear", "item": "ring", "body_loc": "finger"},
                "wear ring finger",
            ),
            (
                "cast_spell",
                {"spell": "cure light wounds", "target": "poucet"},
                "cast 'cure light wounds' poucet",
            ),
            ("shop", {"action": "buy", "args": "1"}, "buy 1"),
            ("save_character", {}, "save"),
        ],
    )
    def test_capability_builds_the_expected_game_line(
            self, name, arguments, line):
        assert build(name, arguments) == line

    def test_a_look_preposition_needs_a_target(self):
        with pytest.raises(ValueError, match="requires target"):
            build("look", {"preposition": "in"})

    def test_an_invalid_enum_is_rejected(self):
        with pytest.raises(ValueError, match="not one of"):
            build("move", {"direction": "sideways"})

    def test_non_wire_capabilities_do_not_build_lines(self):
        with pytest.raises(ValueError, match="does not send"):
            build("poll")


class ScriptedSession:
    def __init__(self, journal: Journal) -> None:
        self.id = "s1"
        self.journal = journal
        self.logged_in = True
        self.lines: list[str] = []

    async def command(self, line: str, *, trace_id=None):
        self.lines.append(line)
        return Reply(line, b"Ok.\r\n", b"", True, 9)

    async def poll(self, *, trace_id=None):
        return Reply("poll", b"A rat arrives.\r\n", b"", True, 10)


@pytest.fixture()
def journal(tmp_path):
    value = Journal(tmp_path / "events.db")
    yield value
    value.close()


class TestTypedExecution:
    async def test_login_seeds_room_and_player_state_without_a_model(
            self, journal):
        session = ScriptedSession(journal)

        await seed_login_observations(session, journal)

        assert session.lines == ["look", "score"]
        probes = journal.since("s1", kind="observer_probe")
        assert [probe.payload for probe in probes] == [
            {"command": "look", "reason": "login_room_state"},
            {"command": "score", "reason": "login_player_state"},
        ]

    async def test_execution_returns_a_typed_observation_and_trace(
            self, journal):
        surface = Surface(load_profile("direct-core"))
        invocation = surface.resolve("look")
        result = await execute(
            ScriptedSession(journal),
            invocation,
            surface,
            journal=journal,
            event_session="s1",
        )
        assert isinstance(result, CommandObservation)
        assert result.capability == "look"
        assert result.command == "look"
        assert result.sequence == 9
        traced = journal.since("s1")
        assert {event.kind for event in traced} == {"tool_call", "tool_result"}
        assert len({event.trace_id for event in traced}) == 1

    async def test_poll_sends_no_game_command(self, journal):
        surface = Surface(load_profile("direct-core"))
        session = ScriptedSession(journal)
        result = await execute(
            session,
            surface.resolve("poll"),
            surface,
            journal=journal,
            event_session="s1",
        )
        assert result.command is None
        assert "rat" in result.text
        assert session.lines == []

    async def test_allowlisted_raw_call_is_traced_as_a_capability_gap(
            self, journal):
        profile = load_profile("direct-full", allow=["send_raw"])
        surface = Surface(profile)
        session = ScriptedSession(journal)
        result = await execute(
            session,
            surface.resolve(
                "send_raw",
                {"line": "look", "reason": "missing typed variant"},
            ),
            surface,
            journal=journal,
            event_session="s1",
        )
        assert result.capability == "send_raw"
        assert session.lines == ["look"]
        gaps = journal.since("s1", kind="capability_gap")
        assert gaps[0].payload["reason"] == "missing typed variant"
        assert gaps[0].trace_id == result.trace_id

    def test_permission_rejection_is_a_typed_error(self):
        surface = Surface(load_profile("direct-core"))
        error = PermissionDenied("cast_spell", surface.profile.id)
        result = failure("cast_spell", error, surface)
        assert isinstance(result, CommandFailure)
        assert result.code == "permission_denied"
        assert result.capability == "cast_spell"
