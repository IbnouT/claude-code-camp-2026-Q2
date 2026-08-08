from typing import Any

from backend.projections.live import _agent_thought


def plan(line: int, text: str) -> dict[str, Any]:
    return {
        "phase": "plan",
        "text": text,
        "line": line,
        "at": f"1970-01-01T00:00:{line:02d}+00:00",
    }


def response(
    line: int,
    stop_reason: str,
    text: str,
) -> dict[str, Any]:
    return {
        "phase": "response",
        "text": text,
        "stop_reason": stop_reason,
        "line": line,
        "at": f"1970-01-01T00:00:{line:02d}+00:00",
    }


def nudge(line: int, instruction: str) -> dict[str, Any]:
    return {
        "phase": "operator_control",
        "action": "guide",
        "instruction": instruction,
        "line": line,
        "at": f"1970-01-01T00:00:{line:02d}+00:00",
    }


WORKING = [
    plan(1, "I need to navigate to the temple."),
    response(2, "tool_use", "(tool use: 1 call)"),
    response(3, "tool_use", "(tool use: 1 call)"),
]
FINISHED = [
    *WORKING,
    plan(4, "Found the fountain. Now I will drink from it."),
    response(5, "tool_use", "(tool use: 1 call)"),
    response(6, "end_turn", "I drank from the fountain in the Midgaard temple."),
]
NUDGED = [
    *FINISHED,
    nudge(7, "find the newbie zone"),
    plan(8, "I will search east from the Great Field."),
    response(9, "tool_use", "(tool use: 1 call)"),
]
FINISHED_AGAIN = [
    *NUDGED,
    response(10, "end_turn", "I found The Entrance To The Newbie Zone."),
]


def test_live_agent_voice_shows_the_latest_planning_while_the_turn_runs():
    thought = _agent_thought(WORKING)

    assert thought is not None
    assert thought.phase == "plan"
    assert thought.text == "I need to navigate to the temple."
    assert thought.evidence == "agent log line 1"


def test_live_agent_voice_shows_the_completion_a_turn_reaches():
    thought = _agent_thought(FINISHED)

    assert thought is not None
    assert thought.phase == "completion"
    assert thought.text == (
        "I drank from the fountain in the Midgaard temple."
    )
    assert thought.observed_at == "1970-01-01T00:00:06+00:00"
    assert thought.evidence == "agent log line 6"


def test_live_agent_voice_returns_to_planning_after_a_nudge():
    thought = _agent_thought(NUDGED)

    assert thought is not None
    assert thought.phase == "plan"
    assert thought.text == "I will search east from the Great Field."


def test_live_agent_voice_ends_on_the_final_completion():
    thought = _agent_thought(FINISHED_AGAIN)

    assert thought is not None
    assert thought.phase == "completion"
    assert thought.text == "I found The Entrance To The Newbie Zone."


def test_live_agent_voice_ignores_a_response_that_stopped_to_call_tools():
    thought = _agent_thought([
        plan(1, "I need to navigate to the temple."),
        response(2, "tool_use", "(tool use: 1 call)"),
        response(3, "end_turn", "   "),
    ])

    assert thought is not None
    assert thought.phase == "plan"
