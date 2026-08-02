"""Repl: the interactive session loop.

It wraps the same primitives as one :func:`run`, but stays alive: it reads a
task, runs a fresh :class:`Agent` over a shared :class:`Context`, prints the
reply, and loops. History accumulates across turns.

Slash commands are handled in the loop and never reach the agent. They are held
in a command table (not an if/elif chain), so ``/help`` is generated from the
table and a new command is one entry plus one handler. A line starting with a
single ``/`` that is not a known command is rejected with a notice rather than
sent to the model. A line starting with ``//`` drops one slash and is sent to
the agent verbatim, so an in-character line that begins with ``/`` still works.

During a turn the REPL subscribes to the logger and prints a live activity feed
(iterations, tool calls, tool results), so a long tool-using turn is not silent.
``/quiet`` suppresses the feed, ``/loud`` restores it, and cost and token totals
accumulate regardless. A turn can be interrupted with Ctrl-C without ending the
session, and any unexpected error in a turn is isolated so the session survives.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

from .agent import Agent
from .backends import backend_for
from .compaction import prefix_tokens
from .errors import ApiError, ConfigError, LoopError, TurnCancelled
from .message import Message
from .objective import ObjectiveContext
from .operator_control import OperatorMailbox, OperatorStopped
from .prompt_builder import PromptBuilder
from .runtime import identity_environment
from .tasks import Player


@dataclass(frozen=True)
class Command:
    """One slash command: its name, aliases, one-line summary, and handler.

    The handler receives the rest of the line (arguments) and returns whether
    the loop should keep running. Only ``/exit`` and ``/quit`` return ``False``.
    """

    name: str
    summary: str
    handler: Callable[[str], bool]
    aliases: tuple[str, ...] = field(default_factory=tuple)


class Repl:
    """Runs the interactive session until the user leaves or input ends."""

    #: What /continue sends. Written into the transcript like any instruction.
    CONTINUE_DIRECTIVE = (
        "Continue from where you stopped. You were cut short by a limit, not "
        "finished. Pick up the same objective without repeating work already done."
    )

    PROMPT = "boukensha> "
    #: Shown while reading a backslash-continued line, so a multi-line message
    #: reads as one visible input.
    CONTINUATION_PROMPT = "......... "

    def __init__(self, *, context: Any, registry: Any, builder: Any,
                 client: Any, logger: Any,
                 task_settings: Any = None,
                 max_iterations: int | None = None,
                 max_output_tokens: int | None = None,
                 thinking: str | None = None,
                 max_turn_tokens: int | None = None,
                 max_turn_cost: float | None = None,
                 config_dir: str | None = None,
                 provider: str | None = None,
                 model: str | None = None,
                 version: str | None = None,
                 api_key: str | None = None,
                 api_key_override: str | None = None,
                 servers: dict[str, int] | None = None,
                 ollama_host: str | None = None,
                 mud_host: str | None = None,
                 mud_port: int | None = None,
                 mud_username: str | None = None,
                 operator: OperatorMailbox | None = None,
                 input: TextIO | None = None,
                 output: TextIO | None = None) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._logger = logger
        self._task_settings = task_settings
        self._max_iterations = max_iterations
        self._max_output_tokens = max_output_tokens
        #: Reasoning-effort override for the session, forwarded to each turn's
        #: Agent. None lets each turn resolve the task's own level.
        self._thinking = thinking
        #: A per-turn token budget, forwarded to the Agent only when set. The
        #: context step is its first user; earlier steps' Agent has no such param.
        self._max_turn_tokens = max_turn_tokens
        self._max_turn_cost = max_turn_cost
        self._config_dir = config_dir
        self._provider = provider
        self._model = model
        self._version = version
        self._api_key = api_key
        #: The raw api_key argument (not the resolved one), so a cross-provider
        #: /model switch can resolve the new provider's own key.
        self._api_key_override = api_key_override
        #: MCP server name -> tool count, shown in the banner. First populated
        #: by the standard tool library step; empty when no servers are wired.
        self._servers = servers or {}
        #: The in-flight turn's cancel event, None between turns.
        self._cancel_event: threading.Event | None = None
        self._ollama_host = ollama_host
        self._mud_host = mud_host
        self._mud_port = mud_port
        self._mud_username = mud_username
        self._operator = operator
        self._operator_stopped = False
        self._input: TextIO = input if input is not None else sys.stdin
        #: Public so the wrapper can print an interrupt notice to the same stream.
        self.output: TextIO = output if output is not None else sys.stdout
        self._turn = 0
        self._quiet = False
        self._show_reasoning = False
        self._tokens_in = 0
        self._tokens_out = 0
        self._cost = 0.0
        self._runtime_identity = identity_environment()

        # The live feed: one subscription for the whole session, since the same
        # Logger flows through every turn's Agent. The Logger guards each
        # subscriber call, so a feed error can never crash a turn.
        self._event_handlers: dict[str, Callable[[dict], None]] = {
            "iteration": self._on_iteration,
            "tool_call": self._on_tool_call,
            "tool_result": self._on_tool_result,
            "response": self._on_response,
            "reasoning": self._on_reasoning,
        }
        #: An optional output sink. A front-end (the TUI) sets it via on_output
        #: to capture the REPL's output instead of a stream.
        self._output_sink: Callable[[str], None] | None = None
        if self._logger is not None:
            self._logger.subscribe(self._on_event)

        self._command_list = self._build_commands()
        self._commands: dict[str, Command] = {}
        for command in self._command_list:
            for token in (command.name, *command.aliases):
                self._commands[token] = command

    # -- command table -----------------------------------------------------

    def _build_commands(self) -> list[Command]:
        return [
            Command("/help", "show this message", self._cmd_help),
            Command("/tools", "list the registered tools", self._cmd_tools),
            Command("/servers", "show the MCP servers and their tool counts", self._cmd_servers),
            Command("/system", "show the system prompt", self._cmd_system),
            Command("/history", "show the conversation so far", self._cmd_history),
            Command("/cost", "show the running USD cost", self._cmd_cost),
            Command("/tokens", "show the running token totals", self._cmd_tokens),
            Command("/quiet", "suppress the live activity feed", self._cmd_quiet),
            Command("/loud", "restore the live activity feed", self._cmd_loud),
            Command("/reasoning", "toggle showing model reasoning", self._cmd_reasoning),
            Command("/model", "show or switch the provider/model", self._cmd_model),
            Command("/mud", "show the configured MUD target", self._cmd_mud),
            Command("/compact", "compact the conversation to fit the context window", self._cmd_compact),
            Command("/limits", "show every ceiling with its usage, or set one",
                    self._cmd_limits),
            Command("/continue", "resume a turn a ceiling cut short",
                    self._cmd_continue),
            Command("/undo", "drop the last turn from history", self._cmd_undo),
            Command("/retry", "drop and rerun the last turn", self._cmd_retry),
            Command("/save", "save the transcript to a file", self._cmd_save),
            Command("/clear", "wipe conversation history (tools stay)", self._cmd_clear),
            Command("/exit", "leave the REPL", self._cmd_exit, aliases=("/quit",)),
        ]

    # -- the loop ----------------------------------------------------------

    def start(self, initial_task: str | None = None) -> None:
        """Print the banner, run an optional first task, then read until EOF."""
        self._write(self.banner())
        if initial_task is not None:
            self.run_turn(initial_task)
            if self._operator_stopped:
                return

        while True:
            self._write(self.PROMPT)
            self.output.flush()

            logical = self._read_logical_line()
            if logical is None:  # EOF / Ctrl-D
                return

            line = logical.strip()
            if not line:
                continue
            if self._handle_operator_wakeup(line):
                if self._operator_stopped:
                    return
                continue

            kind, payload = self.classify_input(line)
            if kind == "command":
                if self.handle_command(payload) == "quit":
                    return
                continue
            self.run_turn(payload)
            if self._operator_stopped:
                return

    @staticmethod
    def classify_input(line: str) -> tuple[str, str]:
        """Classify one input line as a command or an agent turn.

        ``("command", line)`` for a ``/word`` line, ``("turn", line[1:])`` for a
        ``//`` escape (an in-character line that starts with a slash, one slash
        dropped), ``("turn", line)`` otherwise. The single source of truth for
        this branch, used by ``start()`` and by any front-end (the TUI), so a
        second driver can never reimplement it differently.
        """
        if line.startswith("//"):
            return "turn", line[1:]
        if line.startswith("/"):
            return "command", line
        return "turn", line

    def handle_command(self, line: str) -> str | None:
        """Dispatch one slash command. Returns ``"quit"`` if it ends the
        session, ``"command"`` if it handled a known command, or ``None`` for an
        unknown command. Public so a front-end (the TUI) routes the same commands
        through the same table the loop uses."""
        parts = line.split(None, 1)
        name = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        command = self._commands.get(name)
        if command is None:
            self._writeln(f"unknown command: {name} (try /help)")
            return None
        return "command" if command.handler(rest) else "quit"

    def on_output(self, callback: Callable[[str], None]) -> None:
        """Route the REPL's output to a callback instead of the stream. Used by
        a front-end (the TUI) to capture output into its own display."""
        self._output_sink = callback

    def _read_logical_line(self) -> str | None:
        """Read one logical input, joining backslash-continued physical lines.

        A physical line ending in a backslash drops the backslash and continues
        on the next line, so a pasted block or a long multi-line instruction is
        one turn rather than several. Returns the joined text, or ``None`` at end
        of input.
        """
        raw = self._input.readline()
        if raw == "":
            return None
        parts: list[str] = []
        while True:
            physical = raw.rstrip("\n")
            if physical.endswith("\\"):
                parts.append(physical[:-1])
                self._write(self.CONTINUATION_PROMPT)
                self.output.flush()
                raw = self._input.readline()
                if raw == "":  # end of input mid-continuation: use what we have.
                    break
            else:
                parts.append(physical)
                break
        return "\n".join(parts)

    # -- public read surface for a driving front-end -----------------------

    @property
    def context(self) -> Any:
        return self._context

    @property
    def quiet(self) -> bool:
        """Whether the live activity feed is suppressed. A front-end that
        renders the trace itself (the TUI, from logger events) sets this so the
        REPL does not also print the feed into the shared output sink."""
        return self._quiet

    @quiet.setter
    def quiet(self, value: bool) -> None:
        self._quiet = bool(value)

    @property
    def logger(self) -> Any:
        return self._logger

    @property
    def version(self) -> str | None:
        return self._version

    @property
    def model(self) -> str | None:
        return self._model

    @property
    def registry(self) -> Any:
        return self._registry

    @property
    def max_iterations(self):
        """The step ceiling in force, so a front-end can show current over limit."""
        return self._max_iterations

    @property
    def max_turn_tokens(self):
        return self._max_turn_tokens

    @property
    def max_turn_cost(self):
        return self._max_turn_cost

    @property
    def context_window(self):
        """The model's context window from the backend catalog, or None."""
        try:
            return self._builder.backend.context_window
        except Exception:
            return None

    @property
    def servers(self) -> dict[str, int]:
        """The ``{server_name: tool_count}`` summary the banner shows."""
        return dict(self._servers)

    @property
    def turn(self) -> int:
        """The real turn counter. ``/undo`` and ``/retry`` decrement it, so a
        front-end must read this rather than keep a shadow count."""
        return self._turn

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def cost(self) -> float:
        """The session's running USD cost, the number ``/cost`` prints."""
        return self._cost

    @property
    def commands(self) -> tuple:
        """The command table, read-only, for a palette or a help surface."""
        return tuple(self._command_list)

    # -- per-turn execution ------------------------------------------------

    def run_turn(self, text: str) -> None:
        """Run a fresh agent over the shared context, printing the reply.

        A new :class:`Agent` per turn resets the per-turn iteration counter.
        Ctrl-C aborts just this turn and returns to the prompt, and any error is
        isolated to the turn, so the session survives a stuck or bad turn.
        """
        if self._turn == 0:
            self._retain_initial_operator_objective(text)
        self._run_turn(text)

    def _run_turn(self, text: str | None) -> None:
        """Run a normal turn or an operator-only wake turn."""
        self._turn += 1
        if text is not None:
            self._apply_stdin_operator_message(text)
        self._logger.turn(n=self._turn, instruction=text)
        if text is not None:
            self._context.add(Message.user(text))

        # A fresh cancel event per turn: the TUI's Esc sets it from another
        # thread and the agent raises TurnCancelled at its next iteration.
        self._cancel_event = threading.Event()
        agent_kwargs: dict[str, Any] = dict(
            task=Player,
            task_settings=self._task_settings,
            max_iterations=self._max_iterations,
            max_output_tokens=self._max_output_tokens,
            thinking=self._thinking,
            cancel_event=self._cancel_event,
            logger=self._logger,
            operator=self._operator,
        )
        # Forwarded only when set, so a step whose Agent has no such parameter
        # (everything before the context step) is unaffected.
        if self._max_turn_tokens is not None:
            agent_kwargs["max_turn_tokens"] = self._max_turn_tokens
        if self._max_turn_cost is not None:
            agent_kwargs["max_turn_cost"] = self._max_turn_cost
        agent = Agent(self._context, self._registry, self._builder,
                      self._client, **agent_kwargs)
        try:
            reply = agent.run()
        except KeyboardInterrupt:
            # Keep history well-formed: a user message with no assistant reply
            # would break the next request. Record the abort as the reply.
            self._context.add(Message.assistant("[turn aborted by user]"))
            self._writeln("\n[aborted] turn interrupted, still in the REPL")
            return
        except OperatorStopped:
            self._context.add(
                Message.assistant("[agent stopped by authenticated operator]")
            )
            self._operator_stopped = True
            self._writeln("\n[stopped] authenticated operator ended the session")
            return
        except TurnCancelled:
            self._context.add(Message.assistant("[turn cancelled by user]"))
            self._writeln("\n[cancelled] turn cancelled, still in the REPL")
            return
        except (ApiError, LoopError) as exc:
            self._writeln(f"\n[error] {exc}")
            return
        except Exception as exc:  # a REPL's job is to stay alive
            self._writeln(f"\n[error] unexpected: {type(exc).__name__}: {exc}")
            return
        finally:
            self._cancel_event = None

        self._writeln("")
        self._writeln(reply)

    def _handle_operator_wakeup(self, text: str) -> bool:
        """Consume a verified lifecycle wake envelope without user transcript."""
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(value, dict) or value.get("type") != "operator_message":
            return False
        request_id = value.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return False
        retained = self._retained_operator_message(request_id)
        if retained is None:
            return False
        if retained.get("applied_iteration") is not None:
            return True
        if self._operator is None:
            self._writeln("[error] retained operator message has no control channel")
            return True
        self._run_turn(None)
        return True

    def _retained_operator_message(
        self,
        request_id: str,
    ) -> dict[str, Any] | None:
        session_dir = self._runtime_identity.get("session_dir")
        if not session_dir:
            return None
        path = Path(session_dir) / "operator-messages.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        messages = value.get("messages") if isinstance(value, dict) else None
        if not isinstance(messages, list):
            return None
        return next(
            (
                item
                for item in messages
                if isinstance(item, dict)
                and item.get("request_id") == request_id
            ),
            None,
        )

    def _retain_initial_operator_objective(self, text: str) -> None:
        """Complete session-start metadata for a supervised first Goal."""
        session_dir = self._runtime_identity.get("session_dir")
        if not session_dir:
            return
        path = Path(session_dir) / "operator-messages.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        messages = value.get("messages") if isinstance(value, dict) else None
        if not isinstance(messages, list):
            return
        message = next(
            (
                item
                for item in reversed(messages)
                if isinstance(item, dict)
                and item.get("action") == "revise"
                and item.get("instruction") == text
            ),
            None,
        )
        if message is None:
            return
        clue = message.get("clue")
        objective = ObjectiveContext.create(
            text,
            clue=clue if isinstance(clue, str) else None,
            source_kind="operator",
            revision=1,
        )
        self._logger.retain_initial_objective(objective.as_log())

    def _apply_stdin_operator_message(self, text: str) -> None:
        """Mark an idle-turn instruction only when the REPL consumes it."""
        session_dir = self._runtime_identity.get("session_dir")
        if not session_dir:
            return
        path = Path(session_dir) / "operator-messages.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        messages = value.get("messages") if isinstance(value, dict) else None
        if not isinstance(messages, list):
            return
        message = next(
            (
                item
                for item in reversed(messages)
                if isinstance(item, dict)
                and item.get("instruction") == text
                and item.get("applied_iteration") is None
            ),
            None,
        )
        if message is None:
            return
        message["applied_iteration"] = self._turn
        message["applied_at"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_name(".operator-messages.repl.tmp")
        try:
            temporary.write_text(
                json.dumps(value, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)

    def cancel_turn(self) -> bool:
        """Ask the in-flight turn to stop. True when a turn was running.

        Thread-safe: a front-end calls this from its own thread (Esc in the
        TUI); the agent notices at its next iteration boundary.
        """
        event = self._cancel_event
        if event is None:
            return False
        event.set()
        return True

    # -- the live feed -----------------------------------------------------

    def _on_event(self, event: dict) -> None:
        handler = self._event_handlers.get(event.get("phase"))
        if handler is not None:
            handler(event)

    def _on_iteration(self, event: dict) -> None:
        if not self._quiet:
            self._writeln(f"  [iteration {event.get('n')}/{event.get('max')}]")

    def _on_tool_call(self, event: dict) -> None:
        if not self._quiet:
            self._writeln(f"  -> {event.get('name')}({event.get('args')})")

    def _on_tool_result(self, event: dict) -> None:
        preview = self._preview(event.get("result"))
        if not event.get("ok", True):
            self._writeln(f"  <- {event.get('name')} ERROR: {preview}")
        elif not self._quiet:
            self._writeln(f"  <- {event.get('name')}: {preview}")

    def _on_response(self, event: dict) -> None:
        # Accounting is always on, independent of the feed: nobody wants a
        # surprise bill because logging was quiet.
        self._tokens_in += event.get("input_tokens") or 0
        self._tokens_out += event.get("output_tokens") or 0
        self._cost += event.get("cost_usd") or 0.0

    def _on_reasoning(self, event: dict) -> None:
        # Reasoning events are emitted from this step on; show them when
        # /reasoning is on and the feed is not quiet.
        if self._show_reasoning and not self._quiet:
            self._writeln(f"  (thinking) {self._preview(event.get('text'))}")

    # -- command handlers --------------------------------------------------

    def _cmd_help(self, rest: str) -> bool:
        lines = ["Commands:"]
        for command in self._command_list:
            names = " or ".join((command.name, *command.aliases))
            lines.append(f"  {names:20s} {command.summary}")
        lines.append(f"  {'//<text>':20s} send a line starting with / to the agent")
        self._writeln("\n".join(lines))
        return True

    def _cmd_tools(self, rest: str) -> bool:
        tools = self._registry.tools
        if not tools:
            self._writeln("(no tools registered)")
            return True
        self._writeln(f"{len(tools)} tool(s):")
        for tool in tools.values():
            self._writeln(f"  {tool.name} - {tool.description}")
        return True

    def _cmd_servers(self, rest: str) -> bool:
        if not self._servers:
            self._writeln("no MCP servers configured")
            return True
        self._writeln(f"{len(self._servers)} MCP server(s):")
        for name, count in self._servers.items():
            self._writeln(f"  {name}: {count} tool(s)")
        return True

    def _cmd_system(self, rest: str) -> bool:
        self._writeln(self._context.system or "(no system prompt)")
        return True

    def _cmd_history(self, rest: str) -> bool:
        messages = self._context.messages
        if not messages:
            self._writeln("(no history yet)")
            return True
        self._writeln(f"{len(messages)} message(s):")
        for message in messages:
            text = "".join(getattr(b, "text", "") for b in message.content)
            self._writeln(f"  {message.role.value}: {self._preview(text, 80)}")
        return True

    def _cmd_cost(self, rest: str) -> bool:
        self._writeln(f"running cost: ${round(self._cost, 6)}")
        return True

    def _cmd_tokens(self, rest: str) -> bool:
        self._writeln(f"running tokens: {self._tokens_in} in / {self._tokens_out} out")
        return True

    def _cmd_quiet(self, rest: str) -> bool:
        self._quiet = True
        self._writeln("(feed suppressed, type /loud to restore; totals still tracked)")
        return True

    def _cmd_loud(self, rest: str) -> bool:
        self._quiet = False
        self._writeln("(feed restored)")
        return True

    def _cmd_reasoning(self, rest: str) -> bool:
        self._show_reasoning = not self._show_reasoning
        state = "on" if self._show_reasoning else "off"
        self._writeln(f"(reasoning display {state})")
        return True

    def _cmd_model(self, rest: str) -> bool:
        parts = rest.split()
        if not parts:
            self._writeln(f"provider/model: {self._provider} / {self._model}")
            return True
        if len(parts) == 1:
            provider, model = self._provider, parts[0]
        else:
            provider, model = parts[0], parts[1]
        try:
            backend = backend_for(provider, model, api_key=self._api_key_override)
            if self._ollama_host is not None:
                backend.configure_host(self._ollama_host)
            builder = PromptBuilder(
                self._context, backend, tuple(self._registry.tools.values()))
            self._client = self._client.for_builder(builder)
        except (ConfigError, ApiError, ValueError) as exc:
            self._writeln(f"[error] could not switch model: {exc}")
            return True
        self._builder = builder
        self._provider, self._model, self._api_key = provider, model, backend.api_key
        self._writeln(f"(switched to {provider} / {model})")
        return True

    #: The ceilings a person can see and change at runtime, with how each is
    #: measured. A limit nobody can reach is a dead end, which is what playing
    #: step 12 by hand ran into.
    _LIMIT_FIELDS = {
        "iterations": ("_max_iterations", "steps this turn", int),
        "turn_tokens": ("_max_turn_tokens", "tokens processed this turn", int),
        "turn_cost": ("_max_turn_cost", "USD spent this turn", float),
        "window": (None, "context window", int),  # set on the Context
    }

    def _limit_rows(self):
        """Each ceiling as (name, current, limit, unit), current over limit.

        Reporting a numerator with no denominator is what made the ceilings
        invisible: /tokens and /cost showed usage and never what it was against.
        """
        ctx = self._context
        return [
            ("iterations", None, self._max_iterations, "steps"),
            ("turn_tokens", getattr(ctx, "turn_tokens", 0),
             self._max_turn_tokens, "tokens"),
            ("turn_cost", round(getattr(ctx, "turn_cost", 0.0), 6),
             self._max_turn_cost, "USD"),
            ("window", getattr(ctx, "current_tokens", 0),
             getattr(ctx, "context_window", None), "tokens"),
        ]

    def _cmd_limits(self, rest: str) -> bool:
        """Show every ceiling with its usage, or set one: /limits <name> <value>."""
        parts = rest.split()
        if len(parts) >= 2:
            return self._set_limit(parts[0], parts[1])
        if parts:
            self._writeln(f"usage: /limits <name> <value>, names: "
                          f"{', '.join(self._LIMIT_FIELDS)}")
            return True
        self._writeln("limits (current / ceiling):")
        for name, current, limit, unit in self._limit_rows():
            shown = "unset" if limit in (None,) else (
                "disabled" if not limit else f"{limit}")
            got = "-" if current is None else str(current)
            self._writeln(f"  {name:<12} {got:>10} / {shown:<10} {unit}")
        self._writeln("set one with /limits <name> <value>, 0 disables a breaker")
        return True

    def _set_limit(self, name: str, raw: str) -> bool:
        field = self._LIMIT_FIELDS.get(name)
        if field is None:
            self._writeln(f"unknown limit: {name} (one of "
                          f"{', '.join(self._LIMIT_FIELDS)})")
            return True
        attr, meaning, cast = field
        try:
            value = cast(raw)
        except ValueError:
            self._writeln(f"{name} needs a {cast.__name__}, got {raw!r}")
            return True
        if value < 0:
            self._writeln(f"{name} cannot be negative")
            return True
        if name == "window":
            self._context.context_window = value
            self._writeln(f"window set to {value} tokens, compaction at "
                          f"{int(value * self._context.compaction_threshold)}")
            return True
        setattr(self, attr, value)
        note = " (disabled)" if value == 0 else ""
        self._writeln(f"{name} set to {value}{note}, {meaning}. "
                      "Applies from the next turn.")
        return True

    def _cmd_continue(self, rest: str) -> bool:
        """Resume a turn a ceiling cut short.

        The history is intact and the agent already recorded why it stopped, so
        retyping the instruction is a design failure. A visible continuation
        instruction is appended rather than pretending a turn resumes mid-flight:
        providers require the last message to be a user turn and the wind-down
        leaves an assistant message, so something has to be added, and an
        invisible injected message is worse than a visible one.
        """
        self.run_turn(rest.strip() or self.CONTINUE_DIRECTIVE)
        return True

    def _cmd_compact(self, rest: str) -> bool:
        before = self._context.current_tokens
        dropped = self._context.compact_messages(
            overhead=prefix_tokens(self._context.system, self._registry.tools))
        result = self._context.last_compaction
        # Manual /compact logs the same compaction event as auto-compaction, so
        # a manual free is visible to the log and the TUI, not just printed.
        if self._logger is not None and result is not None:
            self._logger.compaction(
                before=before, dropped=dropped,
                compressed=result.compressed, summarized=result.summarized,
                over_budget=result.over_budget,
                context_window=self._context.context_window,
                # Asked for, not triggered by pressure.
                trigger="manual"
            )
        note = f"compacted context, dropped {dropped} message(s)"
        if result is not None and result.compressed:
            note += f", compressed {result.compressed}"
        if result is not None and result.summarized:
            note += ", kept a memory summary"
        self._writeln(note)
        return True

    def _cmd_mud(self, rest: str) -> bool:
        if not self._mud_host:
            self._writeln("(no MUD target configured)")
            return True
        port = f":{self._mud_port}" if self._mud_port else ""
        user = f" as {self._mud_username}" if self._mud_username else ""
        self._writeln(f"MUD target: {self._mud_host}{port}{user}")
        return True

    def _cmd_undo(self, rest: str) -> bool:
        text = self._context.drop_last_turn()
        if text is None:
            self._writeln("(nothing to undo)")
            return True
        self._turn = max(0, self._turn - 1)
        self._writeln(f"(dropped: {self._preview(text, 80)})")
        return True

    def _cmd_retry(self, rest: str) -> bool:
        text = self._context.drop_last_turn()
        if text is None:
            self._writeln("(nothing to retry)")
            return True
        self._turn = max(0, self._turn - 1)
        self._writeln(f"(retrying: {self._preview(text, 80)})")
        self.run_turn(text)
        return True

    def _cmd_save(self, rest: str) -> bool:
        path = Path(rest.strip()) if rest.strip() else self._logger.path.with_suffix(".md")
        try:
            path.write_text(self._render_transcript(), encoding="utf-8")
        except OSError as exc:
            self._writeln(f"[error] could not save: {exc}")
            return True
        self._writeln(f"(saved transcript to {path})")
        return True

    def _cmd_clear(self, rest: str) -> bool:
        self._context.clear_messages()
        self._turn = 0
        self._writeln("(conversation history cleared)")
        return True

    def _cmd_exit(self, rest: str) -> bool:
        self._writeln("Goodbye.")
        return False

    # -- rendering ---------------------------------------------------------

    def _render_transcript(self) -> str:
        lines = [f"# boukensha session {self._logger.session_id}", ""]
        for message in self._context.messages:
            lines.append(f"## {message.role.value}")
            for block in message.content:
                text = getattr(block, "text", None)
                if text is not None:
                    lines.append(text)
                elif getattr(block, "name", None) is not None:
                    args = getattr(block, "input", "")
                    lines.append(f"> tool_call: {block.name}({args})")
                    result = getattr(block, "content", None)
                    if result is not None:
                        lines.append(f"> tool_result: {result}")
            lines.append("")
        return "\n".join(lines)

    def _servers_status(self) -> str:
        if not self._servers:
            return "none"
        return "  ".join(f"{name} ({count})" for name, count in self._servers.items())

    @staticmethod
    def _preview(value: Any, limit: int = 200) -> str:
        text = str(value)
        return text if len(text) <= limit else text[:limit] + "..."

    # -- banner ------------------------------------------------------------

    def banner(self) -> str:
        if self._api_key and self._api_key.strip():
            key_status = "api key set"
        else:
            key_status = "api key not set"

        provider = self._provider or "default"
        model = self._model or "default"

        if self._config_dir and Path(self._config_dir).is_dir():
            config_line = self._config_dir
        else:
            shown = self._config_dir or "(default)"
            config_line = f"{shown}  (directory not found)"

        version = self._version or "?.?.?"
        tool_count = len(self._registry.tools) if self._registry is not None else 0
        player_id = self._runtime_identity.get("player_id")
        session_id = self._runtime_identity.get("session_id")
        identity_line = ""
        if player_id and session_id:
            identity_line = (
                f"  player:    {player_id}\n"
                f"  session:   {session_id}\n"
            )

        return (
            "\n"
            "==================================================\n"
            f"  BOUKENSHA MUD Assistant  (v{version})\n"
            "==================================================\n"
            f"{identity_line}"
            f"  config:    {config_line}\n"
            f"  provider:  {provider} ({model})  {key_status}\n"
            f"  tools:     {tool_count} registered\n"
            f"  servers:   {self._servers_status()}\n"
            "\n"
            "  /help             show all commands\n"
            "  /quiet or /loud   toggle the live activity feed\n"
            "  /exit or /quit    leave the REPL\n"
            "\n"
        )

    #: Back-compat alias: an older caller referenced the banner as ``_banner``.
    _banner = banner

    # -- output helpers ----------------------------------------------------

    def _write(self, text: str) -> None:
        if self._output_sink is not None:
            self._output_sink(text)
        else:
            self.output.write(text)

    def _writeln(self, text: str) -> None:
        self._write(text + "\n")

    def __str__(self) -> str:
        return (
            f"<Repl provider={self._provider} model={self._model} "
            f"turn={self._turn} commands={len(self._command_list)}>"
        )

    __repr__ = __str__
