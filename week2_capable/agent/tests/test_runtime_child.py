from __future__ import annotations

import io
import sys

import pytest

from boukensha import launcher, run_dsl, runtime_child
from boukensha.errors import ConfigError


def test_persistent_initial_task_consumes_one_line_and_keeps_input_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO("Find the bakery.\nNow read the menu.\n")
    captured: dict[str, object] = {}

    monkeypatch.delenv("BOUKENSHA_LAUNCH_TASK", raising=False)
    monkeypatch.setattr(sys, "argv", ["runtime_child", "--initial-task-stdin"])
    monkeypatch.setattr(sys, "stdin", stream)
    monkeypatch.setattr(run_dsl, "repl", lambda **kwargs: captured.update(kwargs))

    runtime_child.main()

    assert captured["initial_task"] == "Find the bakery."
    assert captured["input"] is stream
    assert stream.readline() == "Now read the menu.\n"
    assert captured["tui"] is False


def test_one_shot_launch_task_keeps_using_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setenv("BOUKENSHA_LAUNCH_TASK", "Run once.")
    monkeypatch.setattr(sys, "argv", ["runtime_child", "--no-tui"])
    monkeypatch.setattr(
        run_dsl,
        "run",
        lambda task, **kwargs: captured.update(task=task, **kwargs) or "done",
    )

    runtime_child.main()

    assert captured["task"] == "Run once."


def test_launcher_accepts_only_complete_experiment_correlation() -> None:
    assert launcher._experiment_correlation(
        {
            "BOUKENSHA_EXPERIMENT_ID": "experiment-1",
            "BOUKENSHA_RUN_ID": "sample-1",
        }
    ) == ("experiment-1", "sample-1")
    assert launcher._experiment_correlation({}) == (None, None)
    with pytest.raises(ConfigError, match="requires both"):
        launcher._experiment_correlation({"BOUKENSHA_EXPERIMENT_ID": "experiment-1"})


@pytest.mark.parametrize(
    "arguments",
    [
        ["--task-stdin", "--initial-task-stdin", "--no-tui"],
        ["--initial-task-stdin"],
    ],
)
def test_persistent_initial_task_mode_rejects_ambiguous_launches(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit):
        launcher.main(arguments)
