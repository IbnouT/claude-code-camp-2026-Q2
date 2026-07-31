"""Internal agent child entered only through the runtime launcher."""

from __future__ import annotations

import os

from .loader import main
from .objective import ObjectiveContext


if __name__ == "__main__":
    task = os.environ.get("BOUKENSHA_LAUNCH_TASK")
    if task is None:
        main()
    else:
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
