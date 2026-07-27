#!/usr/bin/env python
"""Launch the log viewer on the real sessions directory and hand over control.

A launcher, so it launches. It scripts nothing and asserts nothing: every systematic
check lives in `tests/`, over fixture logs, hermetic and browser-free.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logviewer.cli import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
