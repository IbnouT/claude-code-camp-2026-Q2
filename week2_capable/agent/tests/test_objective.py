from __future__ import annotations

import json
from pathlib import Path

import pytest

from boukensha.objective import ObjectiveContext
from boukensha.run_dsl import run
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
