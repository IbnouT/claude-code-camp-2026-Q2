"""Internal agent child entered only through the runtime launcher."""

from __future__ import annotations

import os

from .loader import main


if __name__ == "__main__":
    task = os.environ.get("BOUKENSHA_LAUNCH_TASK")
    if task is None:
        main()
    else:
        from .run_dsl import run

        print(run(task, log=os.environ.get("BOUKENSHA_BENCHMARK_LOG")))
