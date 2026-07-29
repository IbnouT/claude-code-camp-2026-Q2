from __future__ import annotations

import asyncio
import json

import pytest

from boukensha.config import Config
from boukensha.errors import ConfigError
from boukensha.journey import JourneyParser, Presenter
from boukensha.tool_result import render_tool_result, view_tool_result
from boukensha.tools.mcp import _build_tool
from boukensha.tui import Tui

from .tui_helper import FakeRepl


ROOM_TEXT = """The Temple of Midgaard
You are in the southern end of the temple hall.
[ Exits: n e s w d ]
20H 100M 82V (news) (motd) >"""


def observation(text: str = ROOM_TEXT) -> str:
    return json.dumps({
        "type": "observation",
        "tool": "look",
        "capability": "look",
        "family": "perception",
        "command": "look",
        "text": text,
        "complete": True,
        "sequence": 63,
        "trace_id": "trace-1",
    })


def result_event(result: str) -> dict[str, object]:
    return {
        "phase": "tool_result",
        "name": "tbamud__look",
        "result": result,
        "ok": True,
        "tool_use_id": "call-1",
    }


def test_typed_observation_exposes_human_text() -> None:
    view = view_tool_result(observation())
    assert view.kind == "observation"
    assert view.complete is True
    assert view.text == ROOM_TEXT


def test_unrelated_json_remains_unchanged() -> None:
    result = '{"text":"belongs to another MCP contract","value":3}'
    assert view_tool_result(result).text == result


def test_typed_error_becomes_a_readable_message() -> None:
    result = "error: " + json.dumps({
        "type": "error",
        "tool": "move",
        "code": "permission_denied",
        "message": "move is not enabled",
    })
    view = view_tool_result(result)
    assert view.is_error
    assert view.text == "permission denied: move is not enabled"


def test_model_rendering_modes_preserve_only_the_selected_fields() -> None:
    result = observation()
    assert render_tool_result(result, "raw") == ROOM_TEXT
    assert json.loads(render_tool_result(result, "minimal")) == {
        "text": ROOM_TEXT,
        "complete": True,
    }
    assert render_tool_result(result, "full") == result


def test_mcp_tool_returns_the_selected_model_shape() -> None:
    class Client:
        def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            return {"text": observation(), "error": False}

    tool = _build_tool(
        Client(),
        {"description": "look", "inputSchema": {"properties": {}}},
        "tbamud__look",
        "look",
        result_mode="raw",
    )
    assert tool.handler() == ROOM_TEXT


def test_config_rejects_an_unknown_result_mode(tmp_path, monkeypatch) -> None:
    (tmp_path / "settings.yaml").write_text(
        "mcp_servers:\n"
        "  mud:\n"
        "    command: gateway\n"
        "    result_mode: compact\n"
    )
    monkeypatch.setenv("BOUKENSHA_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="result_mode"):
        Config()


def test_parser_and_presenter_consume_observation_text() -> None:
    parser = JourneyParser()
    presenter = Presenter()
    event = result_event(observation())

    parser.on_event(event)
    cards = presenter.on_event(event)

    assert parser.state.position == "The Temple of Midgaard"
    assert parser.state.vitals["hp"] == 20
    assert cards[0].title == "The Temple of Midgaard"
    assert cards[0].exits == ["n", "e", "s", "w", "d"]
    assert '"type": "observation"' not in cards[0].body


def test_dashboard_render_contains_room_not_envelope() -> None:
    async def render() -> str:
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test(size=(120, 38)) as pilot:
            repl.logger._cb(result_event(observation()))
            await pilot.pause()
            return app.export_screenshot(title="Gateway observation")

    screenshot = asyncio.run(render())
    assert "Temple" in screenshot
    assert "Midgaard" in screenshot
    assert "southern" in screenshot
    assert "observation&quot;" not in screenshot
