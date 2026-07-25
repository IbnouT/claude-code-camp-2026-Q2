"""Shared fixtures for the step-11 TUI test suite.

Two kinds of double, used deliberately:

- ``build_repl`` assembles the REAL chain (Context, Registry, PromptBuilder,
  Client, Logger, Repl) over a scripted ``StubTransport``, so integration tests
  drive genuine session logic with no network and no key.
- ``FakeRepl`` mirrors only the public surface the Tui drives, so pure
  Tui/Textual tests exercise the front-end wiring with no agent behind it,
  the same shape the reference uses.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STEP_DIR))

from boukensha import run_dsl  # noqa: E402
from boukensha.repl import Repl  # noqa: E402
from boukensha.version import __version__ as PKG_VERSION  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="boukensha-step11-tests-"))

# Hermetic config: tests must never read the developer's real .boukensha (which
# may configure live MCP servers). A minimal tasks-only settings.yaml is pinned
# BEFORE any Config() is built, so offline runs spawn nothing.
import os
_CFG = TMP / "config"
_CFG.mkdir()
(_CFG / "settings.yaml").write_text(
    "tasks:\n  player:\n    provider: anthropic\n    model: claude-haiku-4-5\n")
os.environ["BOUKENSHA_DIR"] = str(_CFG)

# Every assembled logger is kept and closed at exit, so test-built sessions
# never surface unclosed-file ResourceWarnings in the runner's output.
import atexit
_LOGGERS = []
atexit.register(lambda: [lg.close() for lg in _LOGGERS])


class StubTransport:
    """Replays its steps in order; the last step repeats if the script runs out."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        return step


def ok(payload):
    return (200, json.dumps(payload), {})


def end_turn(text, itok=1000, otok=40):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": itok, "output_tokens": otok},
    }


def tool_use(name, tid="toolu_1", args=None, itok=1200, otok=20):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": tid, "name": name, "input": args or {}}],
        "usage": {"input_tokens": itok, "output_tokens": otok},
    }


def add_ping_tool(dsl):
    @dsl.tool("ping", description="a ping tool")
    def ping():
        return "pong"


def build_repl(transport, name, *, setup=None, output=None):
    """Assemble the full chain over a stub transport and wrap it in a Repl."""
    assembled = run_dsl._assemble(
        system=None, model=None, backend=None, api_key=None,
        ollama_host="http://localhost:11434",
        log=str(TMP / f"{name}.jsonl"),
        max_output_tokens=None, setup=setup,
        transport=transport, sleep=lambda _s: None,
    )
    repl = Repl(
        context=assembled.context, registry=assembled.registry,
        builder=assembled.builder, client=assembled.client,
        logger=assembled.logger, task_settings=assembled.task_settings,
        max_iterations=assembled.max_iterations,
        max_output_tokens=assembled.max_output_tokens,
        config_dir=assembled.config_dir, provider=assembled.provider,
        model=assembled.model, version=PKG_VERSION,
        api_key=assembled.backend.api_key, servers=assembled.servers,
        output=output if output is not None else io.StringIO(),
    )
    _LOGGERS.append(assembled.logger)
    return repl, assembled


def pane_text(app, pane_id="conversation"):
    """A RichLog pane's rendered text, joined line per line."""
    from textual.widgets import RichLog
    log = app.query_one(f"#{pane_id}", RichLog)
    return "\n".join("".join(seg.text for seg in strip) for strip in log.lines)


class _FakeLogger:
    def subscribe(self, callback):
        self.callback = callback


class _FakeRegistry:
    tools: dict = {}

    def __len__(self):
        return 0


class FakeRepl:
    """The subset of Repl's public surface the Tui drives, and nothing more.

    Records every call so a test asserts on routing, not rendering. Class-level
    ``classify_input`` is borrowed from the real Repl so the routing under test
    is the production branch.
    """

    PROMPT = Repl.PROMPT
    classify_input = staticmethod(Repl.classify_input)

    version = "0.11.0-test"
    model = "fake-model"
    turn = 0
    tokens_in = 0
    tokens_out = 0
    cost = 0.0
    context_window = None

    def __init__(self):
        self.logger = _FakeLogger()
        self.registry = _FakeRegistry()
        self.servers = {}
        self.commands = ()
        self.command_calls: list[str] = []
        self.turn_calls: list[str] = []
        self.cancel_calls = 0
        self._output_cb = None

    def banner(self):
        return "BANNER-TEXT"

    def on_output(self, callback):
        self._output_cb = callback

    def handle_command(self, line):
        self.command_calls.append(line)
        return "quit" if line.split()[0] in ("/exit", "/quit") else "command"

    def run_turn(self, text):
        self.turn_calls.append(text)

    def cancel_turn(self):
        self.cancel_calls += 1
        return False


class BlockingFakeRepl(FakeRepl):
    """A FakeRepl whose run_turn blocks until cancelled or released.

    Mirrors what an in-flight agent turn looks like from the Tui's side: Esc
    calls ``cancel_turn``, which sets the event the blocked turn waits on.
    """

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run_turn(self, text):
        self.turn_calls.append(text)
        self.started.set()
        self.release.wait(timeout=5)

    def cancel_turn(self):
        self.cancel_calls += 1
        self.release.set()
        return True


class BlockingCommandFakeRepl(FakeRepl):
    """A FakeRepl whose handle_command blocks, to prove commands run off-thread."""

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def handle_command(self, line):
        self.command_calls.append(line)
        self.started.set()
        self.release.wait(timeout=5)
        return "command"
