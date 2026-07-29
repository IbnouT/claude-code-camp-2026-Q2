from __future__ import annotations

import asyncio
import json

from boukensha.journey import JourneyParser, Presenter
from boukensha.journey.tool_result import view_tool_result
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
