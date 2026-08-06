"""Logger: a structured recorder for one session's turns.

One :class:`Logger` writes one JSON Lines file, one complete JSON object per
line, each tagged with ``session_id``, ``at``, and ``phase``. This is a file
logger for machine reading and ``tail``/``grep``, not user-facing display. The
agent's loop drives it: a line per iteration, prompt, model response, tool call,
tool result, and the turn's terminal event.

The response event carries execution metadata (task, provider, model, normalized
token counts, and an estimated USD cost when the model has per-token pricing), so
a session log states exactly which model answered and what it cost.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import Config
from .message import Message, ReasoningBlock, TextBlock, ToolResultBlock, ToolUseBlock
from .runtime import identity_environment

if TYPE_CHECKING:
    from .backends.base import Backend
    from .tasks.base import Task  # pragma: no cover


class Logger:
    """Records one session's turns as JSON Lines under ``sessions/``."""

    #: Directory name under the config directory where session files live.
    DEFAULT_SESSION_DIR = "sessions"

    #: Log schema version, written into session_start so a later consumer (a log
    #: viewer, the Visualizer) can detect the vocabulary it is reading and adapt
    #: or refuse rather than guess.
    SCHEMA_VERSION = 2

    #: Every phase name this logger can emit. A consumer (the log viewer) reads
    #: this to validate or route events without hard-coding the vocabulary, and
    #: bumping it alongside SCHEMA_VERSION keeps the two in step.
    PHASES = (
        "session_start", "turn", "iteration", "limit_reached", "prompt",
        "model_request", "provider_response", "response", "tool_call",
        "tool_result", "reasoning", "plan",
        "compaction", "retry", "turn_end", "raw", "log_error",
        "operator_control",
    )

    def __init__(self, session_id: str | None = None, dir: str | Path | None = None,
                 log: str | Path | None = None,
                 snapshot: dict[str, Any] | None = None,
                 debug: bool = False) -> None:
        self._identity = identity_environment()
        runtime_session_id = self._identity.get("session_id")
        if session_id and runtime_session_id and session_id != runtime_session_id:
            raise ValueError(
                "logger session_id conflicts with the launcher runtime identity"
            )
        self._session_id = session_id or runtime_session_id or self._generate_session_id()
        if log is not None:
            self._path = Path(log)
        else:
            runtime_dir = self._identity.get("session_dir")
            if runtime_dir and dir is None:
                self._path = Path(runtime_dir) / "agent.jsonl"
            else:
                base = Path(dir) if dir is not None else self._default_dir()
                self._path = base / f"{self._session_id}.jsonl"
        self._debug = debug
        #: Count of events dropped because even the log_error fallback failed.
        self._dropped = 0
        #: How many times each turn number has been logged, so a redone turn
        #: is recorded as a repeat rather than as an indistinguishable duplicate.
        self._turn_attempts: dict[int, int] = {}
        #: Callbacks that receive every event, in addition to the JSONL file.
        #: Fan-out only, the file record is unaffected. First consumed by the
        #: TUI (step 11) to drive its progress line without polling.
        self._subscribers: list[Any] = []

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._log_io = open(self._path, "a", encoding="utf-8")

        start: dict[str, Any] = {"phase": "session_start", "schema": self.SCHEMA_VERSION}
        if snapshot:
            start.update(snapshot)
        self._write_log(start)

    # -- read-only identity -----------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def path(self) -> Path:
        return self._path

    # -- phase events ------------------------------------------------------

    def iteration(self, n: int, max: int | None) -> None:
        self._write_log({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, kind: str, n: int, max: int | None) -> None:
        self._write_log({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def state_block_failed(self, error: str) -> None:
        self._write_log({"phase": "state_block_failed", "error": error})

    def turn_end(self, reason: str, iterations: int,
                 tokens: int | None = None, *,
                 input_tokens: int | None = None,
                 output_tokens: int | None = None,
                 cost_usd: float | None = None,
                 duration_ms: float | None = None,
                 usage: dict[str, int] | None = None,
                 unique_tokens: int | None = None,
                 amplification: float | None = None) -> None:
        """Close one turn, with its totals so a viewer needs no re-summing.

        ``input_tokens``/``output_tokens``/``cost_usd`` are the turn's summed
        usage across every model round trip, ``duration_ms`` its wall-clock in
        the model calls. Each is omitted when the agent could not compute it.

        ``usage`` carries the turn's four token classes, and ``unique_tokens``
        with ``amplification`` carry the repetition metric. Amplification is
        WRITTEN rather than left to the reader: the agent counts each distinct
        thing sent once, and that count exists nowhere in the message stream, so
        a reader cannot reconstruct it. A viewer computing its own would be
        inventing a number, not reading one.
        """
        event: dict[str, Any] = {
            "phase": "turn_end",
            "reason": reason,
            "iterations": iterations,
        }
        # Omitted when absent, like every other optional total here. Writing
        # ``"tokens": null`` unconditionally put a null in the record where the
        # convention everywhere else is that the key is simply not there, and it
        # made the field look present in every session while carrying a value in
        # only some.
        if tokens is not None:
            event["tokens"] = tokens
        if input_tokens is not None:
            event["input_tokens"] = input_tokens
        if output_tokens is not None:
            event["output_tokens"] = output_tokens
        if cost_usd is not None:
            event["cost_usd"] = cost_usd
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms)
        if usage:
            event["usage"] = usage
        if unique_tokens is not None:
            event["unique_tokens"] = unique_tokens
        if amplification is not None:
            event["amplification"] = amplification
        self._write_log(event)

    def retry(self, attempt: int, wait: float, status: int | None = None,
              error: str | None = None) -> None:
        """Record one transient-failure retry before the client sleeps.

        ``attempt`` is the attempt that just failed, ``wait`` the delay before
        the next one, and one of ``status`` (a retryable HTTP status) or
        ``error`` (a transport exception) names the trigger. Gives a viewer the
        provider flakiness a bare response never shows.
        """
        self._write_log({
            "phase": "retry", "attempt": attempt, "wait": wait,
            "status": status, "error": error,
        })

    def operator_control(
        self,
        *,
        request_id: str,
        action: str,
        state: str,
        iteration: int,
        instruction: str | None,
    ) -> None:
        """Record an authenticated operator directive when it takes effect."""
        self._write_log(
            {
                "phase": "operator_control",
                "request_id": request_id,
                "action": action,
                "state": state,
                "iteration": iteration,
                "instruction": instruction,
            }
        )

    def turn(self, n: int, instruction: str | None = None) -> None:
        """Mark the start of an interactive turn, one per user input in a REPL session.

        ``n`` is the USER-FACING turn number and is deliberately not unique: `/retry`
        and `/undo` step it back so a redone turn keeps the number it had, which is
        what a person means by redoing turn three.

        So the record says when a number is being reused. ``attempt`` counts them, and
        it is absent on a first attempt rather than written as 1, because absence is
        how everything else optional here reads. Without it a reader has four turns
        labelled 3 and no way to tell they were four, which cost three turns and both
        compaction records their place on screen.
        """
        event: dict[str, Any] = {
            "phase": "turn",
            "n": n,
            "instruction": instruction,
        }
        self._turn_attempts[n] = self._turn_attempts.get(n, 0) + 1
        if self._turn_attempts[n] > 1:
            event["attempt"] = self._turn_attempts[n]
        self._write_log(event)

    def prompt(self, messages: list[Message], tools: Any,
               context_window: int | None = None) -> None:
        names = list(tools.keys()) if isinstance(tools, dict) else list(tools)
        event: dict[str, Any] = {
            "phase": "prompt",
            "message_count": len(messages),
            "messages": [self._serialize_message(m) for m in messages],
            "tool_count": len(names),
            "tools": names,
        }
        if context_window is not None:
            event["context_window"] = context_window
        self._write_log(event)

    def compaction(self, before: int, dropped: int, context_window: int,
                   compressed: int = 0, summarized: bool = False,
                   over_budget: bool = False,
                   trigger: str = "pressure") -> None:
        """Record one context compaction.

        Carries the pre-compaction window pressure, how many messages were dropped,
        how many old tool results were compressed to stubs, whether a memory summary
        was injected, whether the prompt is still over budget afterwards, and the
        model's window.

        ``trigger`` says WHY it happened, and it is not cosmetic. An automatic
        compaction fires when pressure crosses the threshold, and `/compact` fires
        whenever a person asks. Without it the two write an identical record, so a
        reader finding a compaction at four percent of the window has no way to know
        it was requested and reasonably concludes the threshold is broken.
        """
        self._write_log({
            "phase": "compaction",
            "before": before,
            "dropped": dropped,
            "compressed": compressed,
            "summarized": summarized,
            "over_budget": over_budget,
            "context_window": context_window,
            "trigger": trigger,
        })

    def reasoning(self, text: str, redacted: bool = False) -> None:
        """Record one model thinking block, first-class for a log viewer.
        Consumed by context management (step 12)."""
        self._write_log({"phase": "reasoning", "text": self._safe_text(text),
                         "redacted": redacted})

    def model_request(
        self,
        request: dict[str, Any],
        provider: str,
        model: str,
    ) -> None:
        """Record the exact credential-free JSON body sent to the provider."""
        self._write_log({
            "phase": "model_request",
            "provider": provider,
            "model": model,
            "request": request,
        })

    def provider_response(
        self,
        response: dict[str, Any],
        provider: str,
        model: str,
    ) -> None:
        """Record the exact provider JSON before normalization."""
        self._write_log({
            "phase": "provider_response",
            "provider": provider,
            "model": model,
            "response": response,
        })

    def plan(self, text: str) -> None:
        """Record the text preamble the model wrote alongside its tool calls.
        Consumed by context management (step 12)."""
        self._write_log({"phase": "plan", "text": self._safe_text(text).strip()})

    def tool_call(self, name: str, args: dict[str, Any] | None,
                  id: str | None = None) -> None:
        event: dict[str, Any] = {"phase": "tool_call", "name": name, "args": args}
        if id is not None:
            event["id"] = id
        self._write_log(event)

    def tool_result(self, name: str, result: Any, ok: bool = True,
                    error: str | None = None, tool_use_id: str | None = None) -> None:
        event: dict[str, Any] = {
            "phase": "tool_result",
            "name": name,
            "result": self._safe_text(result),
            "ok": ok,
            "error": error,
        }
        stages = getattr(result, "evidence_stages", None)
        if isinstance(stages, dict):
            event["stages"] = stages
        if tool_use_id is not None:
            event["tool_use_id"] = tool_use_id
        self._write_log(event)

    def response(self, text: str, usage: dict[str, Any] | None = None,
                 stop_reason: str | None = None,
                 task: type[Task] | None = None,
                 backend: Backend | None = None,
                 duration_ms: float | None = None,
                 content: tuple[Any, ...] = ()) -> None:
        event: dict[str, Any] = {
            "phase": "response",
            "text": self._safe_text(text).strip(),
            "content": [self._serialize_block(block) for block in content],
            "usage": usage,
            "stop_reason": stop_reason,
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms)
        event.update(self._execution_metadata(task=task, backend=backend, usage=usage))
        self._write_log(event)

    def raw(self, data: Any) -> None:
        """Record the full provider response, only when debug is on."""
        if not self._debug:
            return
        self._write_log({"phase": "raw", "data": data})

    def subscribe(self, callback: Any) -> None:
        """Register a callback that receives every event this logger writes.

        Called after each JSONL line is written and flushed, with the same event
        dict. Fan-out only: the file record is unchanged. First used by the TUI
        (step 11) to update its progress line from log events.
        """
        self._subscribers.append(callback)

    def close(self) -> None:
        if self._log_io is not None and not self._log_io.closed:
            self._log_io.close()

    def retain_initial_objective(
        self,
        objective: dict[str, str | int | None],
    ) -> bool:
        """Add the first operator goal to an otherwise idle session start.

        An interactive runtime writes its session-start record before it can
        receive a first turn. The local supervisor retains a Goal before
        delivering that turn, so the logger can complete the still-solitary
        start record without inferring anything from model or game output.
        """
        try:
            self._log_io.flush()
            records = self._path.read_text(encoding="utf-8").splitlines()
            if len(records) != 1:
                return False
            start = json.loads(records[0])
            if not isinstance(start, dict) or start.get("phase") != "session_start":
                return False
            start["objective"] = dict(objective)
            self._log_io.seek(0)
            self._log_io.truncate()
            self._log_io.write(
                json.dumps(start, separators=(",", ":"), default=str) + "\n"
            )
            self._log_io.flush()
            return True
        except Exception:
            self._dropped += 1
            return False

    def __enter__(self) -> "Logger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- line assembly -----------------------------------------------------

    def _default_dir(self) -> Path:
        return Config.resolve_dir() / self.DEFAULT_SESSION_DIR

    @staticmethod
    def _safe_text(value: Any) -> str:
        """Coerce to text without ever raising.

        A value's own ``__str__`` can fail, and MCP tools return whatever their
        server sends. Coercing at the boundary of a ``try`` is not protection:
        the exception escapes the logger and takes down the run it was only
        supposed to be describing. The logger's contract is that logging never
        breaks the thing being logged, so the coercion has to be inside it.
        """
        try:
            return str(value)
        except Exception as exc:  # noqa: BLE001 - logging must not raise.
            return f"<unprintable {type(value).__name__}: {type(exc).__name__}>"

    def _write_log(self, event: dict[str, Any]) -> None:
        # Logging must never crash the agent turn. A serialization or write
        # failure is recorded as a log_error line instead of raising; if even
        # that fallback fails, the event is counted and dropped.
        try:
            line = dict(event)
            line.update({
                key: value
                for key, value in self._identity.items()
                if key not in {
                    "session_dir",
                    "control_socket",
                    "operator_socket",
                }
            })
            line["session_id"] = self._session_id
            line["at"] = datetime.now().astimezone().isoformat()
            self._log_io.write(
                json.dumps(line, separators=(",", ":"), default=str) + "\n")
            self._log_io.flush()
        except Exception as exc:
            self._write_error(event.get("phase"), exc)
        # Fan the original event out to subscribers after the file write, so a
        # subscriber failure never costs the file record and never crashes the
        # turn. Subscribers see the event without the file-only fields.
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception:
                self._dropped += 1

    def _write_error(self, original_phase: Any, exc: Exception) -> None:
        try:
            line = {
                "phase": "log_error",
                **{
                    key: value
                    for key, value in self._identity.items()
                    if key not in {
                        "session_dir",
                        "control_socket",
                        "operator_socket",
                    }
                },
                "session_id": self._session_id,
                "at": datetime.now().astimezone().isoformat(),
                "original_phase": original_phase,
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._log_io.write(json.dumps(line, default=str) + "\n")
            self._log_io.flush()
        except Exception:
            self._dropped += 1

    @staticmethod
    def _generate_session_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _serialize_message(msg: Message) -> dict[str, Any]:
        return {
            "role": msg.role.value,
            "content": [Logger._serialize_block(b) for b in msg.content],
        }

    @staticmethod
    def _serialize_block(block: Any) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ReasoningBlock):
            return {
                "type": "reasoning",
                "text": block.text,
                "redacted": block.redacted,
            }
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        if isinstance(block, ToolResultBlock):
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "tool_name": block.tool_name,
                "content": block.content,
            }
        # A block type the logger does not know is recorded, not raised: a
        # logging gap must never crash the agent turn.
        return {"type": "unknown", "repr": str(block)}

    # -- execution metadata ------------------------------------------------

    def _execution_metadata(self, task: type[Task] | None,
                            backend: Backend | None,
                            usage: dict[str, Any] | None) -> dict[str, Any]:
        if not (task or backend or usage):
            return {}
        tokens = self._usage_tokens(usage)
        metadata: dict[str, Any] = {
            "task": self._task_name(task),
            "provider": self._provider_name(backend),
            "model": backend.model if backend else None,
            "usage_unit": backend.usage_unit if backend else None,
            "usage_level": backend.usage_level if backend else None,
            "context_window": backend.context_window if backend else None,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": self._estimate_cost(backend, tokens),
        }
        return {k: v for k, v in metadata.items() if v is not None}

    @staticmethod
    def _task_name(task: type[Task] | None) -> str | None:
        if task is None:
            return None
        name = getattr(task, "task_name", None)
        return name if name else str(task)

    @staticmethod
    def _provider_name(backend: Backend | None) -> str | None:
        return backend.provider_name if backend else None

    def _usage_tokens(self, usage: dict[str, Any] | None) -> dict[str, int | None]:
        return self.token_counts(usage)

    @staticmethod
    def token_counts(usage: dict[str, Any] | None) -> dict[str, int | None]:
        """Normalized ``{"input", "output"}`` token counts from any provider's
        usage shape, each ``None`` when absent. Public so the agent can sum turn
        totals with the exact extraction the response metadata uses, no second
        guess at the key names."""
        usage = usage or {}
        return {
            "input": Logger._first_integer(
                usage, "input_tokens", "prompt_tokens",
                "promptTokenCount", "prompt_eval_count",
            ),
            "output": Logger._first_integer(
                usage, "output_tokens", "completion_tokens",
                "candidatesTokenCount", "eval_count",
            ),
        }

    @staticmethod
    def _first_integer(usage: dict[str, Any], *keys: str) -> int | None:
        """The first present key coerced to int, or None on missing/non-integer.

        The first key with a non-null value decides the result: a bad value
        there yields None rather than falling through to a later key, matching
        the reference so one metadata shape covers every provider without a
        surprising second guess.
        """
        for key in keys:
            value = usage.get(key)
            if value is not None:
                if isinstance(value, bool):
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError, OverflowError):
                    return None
        return None

    @staticmethod
    def _estimate_cost(backend: Backend | None,
                       tokens: dict[str, int | None]) -> float | None:
        if backend is None:
            return None
        if tokens["input"] is None or tokens["output"] is None:
            return None
        return backend.estimate_cost(tokens["input"], tokens["output"])

    def __str__(self) -> str:
        return f"<Logger session_id={self._session_id} path={self._path}>"

    __repr__ = __str__
