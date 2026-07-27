"""Shared fixtures for the step-12 context-management suite.

``build_agent`` assembles the REAL chain (Context, Registry, PromptBuilder,
Client, Logger, Agent) over a scripted ``StubTransport``, so a test drives the
genuine turn loop with no network and no key. That is what lets the breaker,
compaction, and usage tests assert behavior end to end rather than a helper in
isolation.

``RecordingLogger`` captures emitted events so a test can assert what the loop
logged (``limit_reached`` kinds, ``turn_end`` reasons, normalized stop reasons)
without reading a file back.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STEP_DIR))

TMP = Path(tempfile.mkdtemp(prefix="boukensha-step12-tests-"))

# Hermetic config: tests must never read the developer's real .boukensha, which
# may configure live MCP servers. A minimal tasks-only settings.yaml is pinned
# BEFORE any Config() is built, so offline runs spawn nothing.
import os  # noqa: E402
_CFG = TMP / "config"
_CFG.mkdir()
(_CFG / "settings.yaml").write_text(
    "tasks:\n  player:\n    provider: anthropic\n    model: claude-haiku-4-5\n")
os.environ["BOUKENSHA_DIR"] = str(_CFG)

from boukensha import run_dsl  # noqa: E402
from boukensha.agent import Agent  # noqa: E402

# Every assembled logger is closed at exit, so test-built sessions never surface
# unclosed-file ResourceWarnings in the runner's output.
import atexit  # noqa: E402
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
        "content": [{"type": "tool_use", "id": tid, "name": name,
                     "input": args or {}}],
        "usage": {"input_tokens": itok, "output_tokens": otok},
    }


def add_ping_tool(dsl):
    @dsl.tool("ping", description="a ping tool")
    def ping():
        return "pong"


class RecordingLogger:
    """Captures every event the loop emits, and swallows nothing else."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []
        self.on_retry = None

    def _record(self, phase):
        def emit(**kwargs):
            self.events.append((phase, kwargs))
        return emit

    def __getattr__(self, name):
        # Any logger method the loop calls is recorded by name.
        if name.startswith("_"):
            raise AttributeError(name)
        return self._record(name)

    def kinds(self, phase):
        return [kw for ph, kw in self.events if ph == phase]

    def close(self):
        pass


def build_agent(transport, name, *, setup=None, logger=None,
                context_window=None, **agent_kwargs):
    """Assemble the real chain over a stub transport and return (agent, assembled)."""
    assembled = run_dsl._assemble(
        system=None, model=None, backend=None, api_key=None,
        ollama_host="http://localhost:11434",
        log=str(TMP / f"{name}.jsonl"),
        max_output_tokens=None, context_window=context_window, setup=setup,
        transport=transport, sleep=lambda _s: None,
    )
    used_logger = logger if logger is not None else assembled.logger
    agent = Agent(
        assembled.context, assembled.registry, assembled.builder,
        assembled.client,
        task=None, task_settings=assembled.task_settings,
        logger=used_logger,
        **agent_kwargs,
    )
    _LOGGERS.append(assembled.logger)
    return agent, assembled
