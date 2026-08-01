from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from boukensha.objective import ObjectiveContext
from boukensha.run_dsl import repl, run
from .helper import StubTransport, end_turn, ok


def test_objective_context_round_trips_without_changing_the_task() -> None:
    task = (
        "Travel north from the Temple into the newbie zone and find the "
        "Massive Minotaur."
    )
    objective = ObjectiveContext.create(
        task,
        title="Find the Massive Minotaur",
        clue="north of the Temple · newbie area",
        source_kind="benchmark",
        revision=1,
    )

    decoded = ObjectiveContext.decode(objective.encode(), task=task)

    assert decoded == objective
    assert decoded.title != task
    assert json.loads(objective.encode()) == {
        "clue": "north of the Temple · newbie area",
        "revision": 1,
        "source_kind": "benchmark",
        "title": "Find the Massive Minotaur",
    }


def test_objective_context_defaults_to_the_exact_operator_task() -> None:
    objective = ObjectiveContext.create("  Explore the eastern field.  ")

    assert objective.title == "Explore the eastern field."
    assert objective.clue is None
    assert objective.source_kind == "operator"
    assert objective.revision == 1


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"task": "", "title": None}, "title cannot be empty"),
        ({"task": "x", "revision": 0}, "revision must be positive"),
    ],
)
def test_objective_context_rejects_invalid_metadata(
    values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ObjectiveContext.create(**values)


def test_run_retains_objective_metadata_beside_the_exact_prompt(
    tmp_path: Path,
) -> None:
    task = (
        "Travel north from the Temple into the newbie zone and find the "
        "Massive Minotaur."
    )
    objective = ObjectiveContext.create(
        task,
        title="Find the Massive Minotaur",
        clue="north of the Temple · newbie area",
        source_kind="benchmark",
    )
    log = tmp_path / "agent.jsonl"

    run(
        task,
        log=str(log),
        objective_context=objective,
        transport=StubTransport(ok(end_turn("done"))),
        sleep=lambda _: None,
    )

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    session_start = records[0]
    prompt = next(record for record in records if record["phase"] == "prompt")
    assert session_start["objective"] == objective.as_log()
    assert prompt["messages"][-1]["content"][-1]["text"] == task


@pytest.mark.parametrize(("action", "retains_objective"), [
    ("revise", True),
    ("guide", False),
])
def test_idle_session_first_message_respects_goal_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    retains_objective: bool,
) -> None:
    task = "Go to the warrior guild."
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "operator-messages.json").write_text(
        json.dumps({
            "version": 1,
            "messages": [{
                "request_id": "goal-1",
                "action": action,
                "instruction": task,
                "sent_at": "2026-08-01T00:00:00Z",
                "applied_iteration": 1,
                "applied_at": "2026-08-01T00:00:01Z",
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOUKENSHA_SESSION_DIR", str(session_dir))
    log = session_dir / "agent.jsonl"

    repl(
        log=str(log),
        transport=StubTransport(ok(end_turn("done"))),
        sleep=lambda _: None,
        tui=False,
        input=io.StringIO(task + "\n"),
        output=io.StringIO(),
    )

    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert records[0]["phase"] == "session_start"
    if retains_objective:
        assert records[0]["objective"] == {
            "title": task,
            "clue": None,
            "source_kind": "operator",
            "revision": 1,
        }
    else:
        assert "objective" not in records[0]
    assert [record["phase"] for record in records].count("session_start") == 1
