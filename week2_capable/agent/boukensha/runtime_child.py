"""Internal agent child entered only through the runtime launcher."""

from __future__ import annotations

import os
import sys

from .loader import main as loader_main
from .objective import ObjectiveContext


def main() -> None:
    """Select the one-shot runner or one of the persistent interactive modes."""
    task = os.environ.get("BOUKENSHA_LAUNCH_TASK")
    initial_task_stdin = "--initial-task-stdin" in sys.argv
    if task is not None and initial_task_stdin:
        raise SystemExit(
            "one-shot and persistent initial tasks are mutually exclusive"
        )
    if task is not None:
        from .run_dsl import run

        raw_objective = os.environ.get("BOUKENSHA_OBJECTIVE_CONTEXT")
        objective = (
            ObjectiveContext.decode(raw_objective, task=task)
            if raw_objective is not None
            else ObjectiveContext.create(task)
        )
        print(
            run(
                task,
                log=os.environ.get("BOUKENSHA_BENCHMARK_LOG"),
                objective_context=objective,
            )
        )
    elif initial_task_stdin:
        from .run_dsl import repl

        initial_task = sys.stdin.readline().strip()
        if not initial_task:
            raise SystemExit("--initial-task-stdin received an empty task")
        objective = ObjectiveContext.create(initial_task)
        repl(
            log=os.environ.get("BOUKENSHA_BENCHMARK_LOG"),
            tui=False,
            input=sys.stdin,
            initial_task=initial_task,
            objective_context=objective,
        )
    else:
        loader_main()


if __name__ == "__main__":
    main()
