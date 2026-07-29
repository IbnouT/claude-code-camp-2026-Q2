"""Capability coverage against the installed manager's recorded tools/list."""

import json
import pathlib

from mud_gateway.commands import BY_NAME, IMMORTAL
from mud_gateway.profiles import PROFILES, Surface

REFERENCE = pathlib.Path(__file__).parent / "fixtures" / "mud_manager_tools.json"
REFERENCE_TOOLS = json.loads(REFERENCE.read_text(encoding="utf-8"))
REFERENCE_NAMES = {
    tool["name"] for tool in REFERENCE_TOOLS
}
REFERENCE_AGENT_NAMES = REFERENCE_NAMES - {"send_raw"}


def comparable(schema):
    properties = {
        name: {
            key: value
            for key, value in definition.items()
            if key in {"type", "enum", "default"}
        }
        for name, definition in schema.get("properties", {}).items()
    }
    return {
        "properties": properties,
        "required": sorted(schema.get("required", [])),
    }


def test_recorded_reference_contains_all_26_capabilities():
    assert len(REFERENCE_NAMES) == 26
    assert "send_raw" in REFERENCE_NAMES


def test_registry_covers_every_evidenced_capability():
    assert REFERENCE_NAMES <= set(BY_NAME)


def test_agent_surface_exactly_covers_the_25_typed_tools():
    profile = PROFILES["direct-full"]
    assert profile.allowed == REFERENCE_AGENT_NAMES
    assert len(Surface(profile).schemas()) == 25


def test_each_agent_tool_matches_name_and_argument_shape():
    residual = {}
    for reference in REFERENCE_TOOLS:
        name = reference["name"]
        if name == "send_raw":
            continue
        expected = comparable(reference["inputSchema"])
        actual = comparable(BY_NAME[name].schema()["inputSchema"])
        if actual != expected:
            residual[name] = {"expected": expected, "actual": actual}
    assert residual == {}


def test_raw_is_supported_but_denied_by_default():
    assert "send_raw" in BY_NAME
    assert "send_raw" not in PROFILES["direct-full"].allowed
    assert {
        argument.name for argument in BY_NAME["send_raw"].arguments
    } == {"line", "reason"}


def test_mortal_surface_has_no_immortal_or_admin_operation():
    advertised = {
        schema["name"]
        for schema in Surface(PROFILES["direct-full"]).schemas()
    }
    assert not advertised & IMMORTAL
    assert not {"admin", "reset", "goto", "restore", "transfer"} & advertised


def test_observe_and_navigate_are_our_extensions_not_reference_tools():
    assert {"observe", "navigate"} <= set(BY_NAME)
    assert not {"observe", "navigate"} & REFERENCE_NAMES
