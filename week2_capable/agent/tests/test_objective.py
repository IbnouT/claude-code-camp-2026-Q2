from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from boukensha.objective import ObjectiveContext
from boukensha.operator_control import OperatorMailbox, OperatorMessageJournal
from boukensha.repl import Repl
from boukensha import run_dsl
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


def test_persistent_initial_task_runs_before_later_repl_turns(
    tmp_path: Path,
) -> None:
    initial = "Find the bakery."
    follow_up = "Now read the menu."
    objective = ObjectiveContext.create(initial)
    log = tmp_path / "agent.jsonl"

    repl(
        log=str(log),
        transport=StubTransport(
            ok(end_turn("At the bakery.")),
            ok(end_turn("Menu read.")),
        ),
        sleep=lambda _: None,
        tui=False,
        input=io.StringIO(follow_up + "\n"),
        output=io.StringIO(),
        initial_task=initial,
        objective_context=objective,
    )

    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert records[0]["objective"] == objective.as_log()
    assert [record["phase"] for record in records].count("session_start") == 1
    assert [record["n"] for record in records if record["phase"] == "turn"] == [
        1,
        2,
    ]
    prompts = [record for record in records if record["phase"] == "prompt"]
    assert prompts[0]["messages"][-1]["content"][-1]["text"] == initial
    assert prompts[-1]["messages"][-1]["content"][-1]["text"] == follow_up


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
                "applied_iteration": None,
                "applied_at": None,
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
    history = json.loads(
        (session_dir / "operator-messages.json").read_text(encoding="utf-8")
    )
    assert history["messages"][0]["applied_iteration"] == 1
    assert history["messages"][0]["applied_at"] is not None


def test_operator_wakeup_starts_a_turn_without_polluting_the_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    monkeypatch.setenv("BOUKENSHA_SESSION_DIR", str(session_dir))
    mailbox = OperatorMailbox(OperatorMessageJournal(session_dir))
    mailbox.submit(
        request_id="goal-1",
        action="revise",
        instruction="Find a peacekeeper.",
    )
    assembled = run_dsl._assemble(
        system=None,
        model=None,
        backend=None,
        api_key=None,
        ollama_host="http://localhost:11434",
        log=str(session_dir / "agent.jsonl"),
        max_output_tokens=None,
        context_window=None,
        setup=None,
        transport=StubTransport(ok(end_turn("done"))),
        sleep=lambda _: None,
    )
    session = Repl(
        context=assembled.context,
        registry=assembled.registry,
        builder=assembled.builder,
        client=assembled.client,
        logger=assembled.logger,
        task_settings=assembled.task_settings,
        max_iterations=assembled.max_iterations,
        max_output_tokens=assembled.max_output_tokens,
        config_dir=assembled.config_dir,
        provider=assembled.provider,
        model=assembled.model,
        version="test",
        api_key=assembled.backend.api_key,
        servers=assembled.servers,
        operator=mailbox,
        input=io.StringIO(
            json.dumps({
                "type": "operator_message",
                "request_id": "goal-1",
            }) + "\n"
        ),
        output=io.StringIO(),
    )
    try:
        session.start()
    finally:
        assembled.logger.close()

    records = [
        json.loads(line)
        for line in (session_dir / "agent.jsonl").read_text().splitlines()
    ]
    prompt = next(record for record in records if record["phase"] == "prompt")
    prompt_text = prompt["messages"][-1]["content"][-1]["text"]
    assert "Find a peacekeeper." in prompt_text
    assert "operator_message" not in prompt_text
    turn = next(record for record in records if record["phase"] == "turn")
    assert turn["instruction"] == "Find a peacekeeper."
    history = json.loads(
        (session_dir / "operator-messages.json").read_text(encoding="utf-8")
    )
    assert history["messages"][0]["applied_iteration"] == 0
