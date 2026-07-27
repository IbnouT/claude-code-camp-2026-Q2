"""A FakeRepl mirroring only the public surface the Tui drives.

Pure front-end tests need no agent behind them, so this records what the Tui asks
for and returns what a real Repl would emit through its output sink.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STEP_DIR))

from boukensha.repl import Repl  # noqa: E402


class _Logger:
    def subscribe(self, callback):
        self._cb = callback

    def __getattr__(self, name):
        return lambda **kw: None


class FakeRepl:
    PROMPT = Repl.PROMPT

    def __init__(self, command_output="ok", turn_output="a reply"):
        self._command_output = command_output
        self._turn_output = turn_output
        self.turn_calls: list[str] = []
        self.command_calls: list[str] = []
        self.cancel_calls = 0
        self.turn = 0
        self.cost = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.quiet = False
        self.context_window = 200_000
        self.context = None
        self.logger = _Logger()
        self.registry = {"look": object()}
        self.servers = {"mud": 1}
        self.commands = ()
        self.version = "test"
        self.model = "test-model"
        self._sink = None
        self.started = threading.Event()

    def on_output(self, callback):
        self._sink = callback

    def banner(self):
        return "fake banner"

    def handle_command(self, line):
        self.command_calls.append(line)
        if line.split()[0] in ("/exit", "/quit"):
            return "quit"
        if self._sink:
            self._sink(self._command_output)
        return "command"

    def run_turn(self, text):
        self.turn_calls.append(text)
        self.turn += 1
        if self._sink:
            self._sink(self._turn_output)

    def cancel_turn(self):
        self.cancel_calls += 1
        return False
