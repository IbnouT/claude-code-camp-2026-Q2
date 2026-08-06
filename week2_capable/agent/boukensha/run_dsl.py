"""The entry points: ``run`` for one turn, ``repl`` for an interactive session.

``run(task=..., setup=...)`` resolves configuration, builds the whole chain
(Context, Registry, backend, PromptBuilder, Client, Logger, Agent), seeds the
task as the first user message, runs one turn, and returns the final text.

``repl(setup=...)`` builds the same chain, then hands it to a :class:`Repl`
that reads tasks from the user, runs the agent, prints the reply, and loops.
One ``Context`` is shared across every turn so history accumulates.

Both entry points wire an identical chain, so the wiring lives once in
``_assemble`` and each entry point calls it. ``RunDSL`` is the small host handed
to ``setup``: it exposes exactly one public method, ``tool``, so a caller
registers ad-hoc tools inline without reaching the registry behind it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, NamedTuple, TextIO

from .agent import Agent
from .backends import Backend, backend_for
from .client import Client, Transport
from .config import Config
from .context import Context
from .errors import ConfigError, McpServerError, McpToolCollisionError
from .logger import Logger
from .message import Message
from .operator_control import OperatorStopped, start_operator_control
from .objective import ObjectiveContext
from .prompt_builder import PromptBuilder
from .registry import Registry
from .repl import Repl
from .session_control import (
    SessionControlError,
    relocate_selected_session,
    reset_selected_session,
)
from .campaign import CampaignController
from .state_fields import CONTRACT as STATE_FIELDS_CONTRACT
from .tasks import Player
from .tools import mcp as mcp_host
from .version import __version__


def _register_mcp_servers(registry: Registry,
                          servers: dict[str, dict[str, Any]],
                          *, err: TextIO = sys.stderr) -> dict[str, int]:
    """Spawn each configured MCP server and register its tools.

    This is the agent's only source of tools: boukensha ships none. Servers are
    spawned in config order. Returns ``{name: tool_count}`` for those that came
    up.

    - A tool-name collision always propagates: it is a config contradiction, not
      an unreachable server, and ``required: false`` does not excuse it.
    - Any other spawn failure raises :class:`McpServerError` naming the server
      when it is required, or warns to ``err`` and continues when it is optional.
    """
    summary: dict[str, int] = {}
    for name, entry in servers.items():
        try:
            before = len(registry.tools)
            mcp_host.register(
                registry,
                entry["command"],
                args=entry["args"],
                env=entry["env"],
                prefix=entry["prefix"],
                timeout=entry["timeout"],
                allow=entry["allow"],
                deny=entry["deny"],
                result_mode=entry["result_mode"],
                inherit_env=entry["inherit_env"],
            )
            # Count what this server actually contributed, after any allow/deny
            # filtering, not everything it advertised.
            summary[name] = len(registry.tools) - before
        except McpToolCollisionError:
            raise
        except Exception as exc:
            if entry["required"]:
                raise McpServerError(
                    f"boukensha: MCP server '{name}' failed to start: {exc}"
                ) from exc
            print(
                f"[boukensha] optional MCP server '{name}' failed to start: "
                f"{exc}, continuing without its tools",
                file=err,
            )
    return summary


class RunDSL:
    """The host passed to a ``run`` or ``repl`` setup callable.

    Wraps the registry with a single narrowing method. The registry stays the
    tool owner (established architecture); ``RunDSL`` is a narrow view over it,
    never a second owner, and exposes nothing else.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def tool(self, name: str, *, description: str,
             parameters: dict[str, Any] | None = None
             ) -> Callable[[Callable], Callable]:
        """Register a tool inline, delegating to ``Registry.tool``."""
        return self._registry.tool(name, description, parameters or {})

    def __str__(self) -> str:
        return f"<RunDSL registry={self._registry}>"

    __repr__ = __str__


class _Assembled(NamedTuple):
    """The wired chain both entry points share, plus the values a banner needs."""

    context: Context
    registry: Registry
    builder: PromptBuilder
    client: Client
    logger: Logger
    backend: Backend
    task_settings: Any
    max_iterations: int | None
    max_turn_tokens: int
    max_turn_cost: float
    max_output_tokens: int | None
    config_dir: str
    provider: str
    model: str
    servers: dict[str, int]
    config: Any = None


def _assemble(*,
              system: str | None,
              model: str | None,
              backend: str | None,
              api_key: str | None,
              ollama_host: str,
              log: str | None,
              max_iterations: int | None = None,
              max_output_tokens: int | None,
              context_window: int | None,
              setup: Callable[[RunDSL], None] | None,
              transport: Transport | None,
              sleep: Callable[[float], None] | None,
              objective_context: ObjectiveContext | None = None) -> _Assembled:
    """Resolve config and build the full primitive chain once.

    Returns every piece ``run`` and ``repl`` need: the wired components, the
    per-turn limits, and the banner values. The offline seam (``transport``,
    ``sleep``) is carried into the ``Client`` so both entry points stay
    verifiable without a network or a key.
    """
    cfg = Config()
    task_settings = cfg.tasks(Player.task_name)

    if system is None:
        system = Player.system_prompt(
            task_settings,
            override_path=cfg.user_prompt_path(Player.task_name),
        )
    if cfg.capability("knowledge"):
        system = f"{system}\n\n{STATE_FIELDS_CONTRACT}"
    if model is None:
        model = Player.model(task_settings)
    if backend is None:
        backend = Player.provider(task_settings)

    # Layered resolution (decision A4a): explicit arg, then the per-task value,
    # then the top-level `agent:` block default, then the code default.
    if max_iterations is None:
        effective_max_iterations = Player.max_iterations(
            task_settings, default=cfg.agent_setting("max_iterations"))
    else:
        effective_max_iterations = max_iterations
    effective_max_turn_tokens = Player.max_turn_tokens(
        task_settings, default=cfg.agent_setting("max_turn_tokens"))
    # Resolved the same way as its four siblings. It was the one ceiling that read
    # task settings alone, so a person wanting one money ceiling across every task had
    # nowhere to put it, and the settings table promised otherwise.
    effective_max_turn_cost = Player.max_turn_cost(
        task_settings, default=cfg.agent_setting("max_turn_cost"))
    effective_compaction_threshold = Player.compaction_threshold(
        task_settings, default=cfg.agent_setting("compaction_threshold"))
    if max_output_tokens is None:
        effective_max_output_tokens = Player.max_output_tokens(
            task_settings, default=cfg.agent_setting("max_output_tokens"))
    else:
        effective_max_output_tokens = max_output_tokens

    # The backend is built first so the context window can be sized from its
    # catalog entry. An unknown model raises ConfigError here, naming the fix.
    be = backend_for(backend, model, api_key=api_key)
    be.configure_host(ollama_host)

    # The window comes from the model unless an explicit context_window= overrides
    # it. The catalog accessor on the backend already answers this, so no
    # standalone Models.context_window module is added.
    window = context_window if context_window is not None else be.context_window
    ctx = Context(
        system, context_window=window,
        compaction_threshold=effective_compaction_threshold,
    )
    registry = Registry()
    # MCP tools are registered before setup, so an inline tool a setup callable
    # adds collides against an MCP tool exactly as two servers would, and both
    # are present when the prompt builder snapshots the toolset below.
    servers = _register_mcp_servers(registry, cfg.mcp_servers())
    reset_baseline = os.environ.get("BOUKENSHA_RESET_BASELINE")
    relocate_temple = os.environ.get("BOUKENSHA_RELOCATE_TEMPLE") == "1"
    if reset_baseline and relocate_temple:
        raise ConfigError("reset baseline and Temple relocation cannot both run")
    if reset_baseline:
        session_dir = os.environ.get("BOUKENSHA_SESSION_DIR")
        if not session_dir:
            raise ConfigError(
                "a reset baseline requires the launcher runtime session"
            )
        try:
            reset_selected_session(
                Path(session_dir),
                reset_baseline,
                timeout=float(
                    os.environ.get("BOUKENSHA_RESET_CLIENT_TIMEOUT", "45")
                ),
            )
        except SessionControlError as error:
            raise ConfigError(f"gateway reset failed: {error}") from error
    elif relocate_temple:
        session_dir = os.environ.get("BOUKENSHA_SESSION_DIR")
        if not session_dir:
            raise ConfigError(
                "Temple relocation requires the launcher runtime session"
            )
        try:
            relocate_selected_session(
                Path(session_dir),
                timeout=float(
                    os.environ.get("BOUKENSHA_RESET_CLIENT_TIMEOUT", "45")
                ),
            )
        except SessionControlError as error:
            raise ConfigError(f"gateway relocation failed: {error}") from error
    if setup is not None:
        setup(RunDSL(registry))

    builder = PromptBuilder(ctx, be, tuple(registry.tools.values()))
    client = Client(builder, transport=transport, sleep=sleep)
    snapshot: dict[str, Any] = {
        "task": Player.task_name,
        "system": system,
        "max_iterations": effective_max_iterations,
        "max_turn_tokens": effective_max_turn_tokens,
        "max_turn_cost": effective_max_turn_cost,
        "max_output_tokens": effective_max_output_tokens,
        "context_window": window,
        "model": model,
        "provider": backend,
        # The per-class rates this session was billed at. A fact about the model
        # rather than about the run, and recorded because a READER cannot get it
        # any other way: a log viewer that owned its own price table would be a
        # second cost calculation, and the one thing it must never do is disagree
        # with the bill. None on an unpriced model, which is not a zero.
        "rates": be.rates,
        "cache_min_tokens": be.cache_min_tokens,
        "caches": be.caches,
    }
    if objective_context is not None:
        snapshot["objective"] = objective_context.as_log()
    logger = Logger(log=log, snapshot=snapshot)

    return _Assembled(
        context=ctx,
        registry=registry,
        builder=builder,
        client=client,
        logger=logger,
        backend=be,
        task_settings=task_settings,
        max_iterations=effective_max_iterations,
        max_turn_tokens=effective_max_turn_tokens,
        max_turn_cost=effective_max_turn_cost,
        max_output_tokens=effective_max_output_tokens,
        config_dir=str(cfg.dir),
        provider=backend,
        model=model,
        servers=servers,
        config=cfg,
    )


def _state_block_source(cfg, registry: Registry):
    """The knowledge state-block fetcher, or None when the flag is off.

    The block is served by the gateway's recall_state tool, whichever
    prefixed name it registered under. A configured flag with no such tool
    yields None rather than a broken agent.
    """
    if cfg is None or not cfg.capability("knowledge"):
        return None
    names = [
        name for name in registry.tools
        if name == "recall_state" or name.endswith("_recall_state")
    ]
    if not names:
        return None
    tool_name = names[0]

    def fetch() -> str | None:
        result = registry.dispatch(tool_name)
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text
        return result if isinstance(result, str) else None

    return fetch


def _state_fields_sink(cfg, registry: Registry):
    """Forwards parsed STATE fields to the gateway, or None when off."""
    if cfg is None or not cfg.capability("knowledge"):
        return None
    names = [
        name for name in registry.tools
        if name == "note_state" or name.endswith("_note_state")
    ]
    if not names:
        return None
    tool_name = names[0]

    def forward(fields: dict) -> None:
        arguments = {
            name: value for name, value in fields.items()
            if value is not None
        }
        registry.dispatch(tool_name, arguments)

    return forward


def _campaign_line_source(cfg, registry: Registry):
    """The campaign controller's line source, or None when off."""
    if cfg is None or not cfg.capability("campaign"):
        return None
    settings = cfg.capability_settings("campaign")
    if not str(settings.get("target", "")).strip():
        return None
    names = [
        name for name in registry.tools
        if name == "mission_readiness"
        or name.endswith("_mission_readiness")
    ]
    if not names:
        return None
    tool_name = names[0]
    target = str(settings["target"]).strip()

    def fetch() -> str | None:
        result = registry.dispatch(tool_name, {"target": target})
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text
        return result if isinstance(result, str) else None

    return CampaignController(fetch, settings).line


def run(task: str, *,
        system: str | None = None,
        model: str | None = None,
        backend: str | None = None,
        api_key: str | None = None,
        ollama_host: str = "http://localhost:11434",
        log: str | None = None,
        max_iterations: int | None = None,
        max_output_tokens: int | None = None,
        thinking: str | None = None,
        context_window: int | None = None,
        objective_context: ObjectiveContext | None = None,
        setup: Callable[[RunDSL], None] | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None) -> str:
    """Wire every primitive and run one turn, returning the final text.

    Options:
      task:              the user message handed to the agent (required).
      system:            system prompt, default the Player task's prompt.
      model:             model name, default the Player task's model.
      backend:           provider name, default the Player task's provider.
      api_key:           key for the backend, default the backend's named env
                         variable (loaded from .boukensha/.env). Not needed to
                         build a backend or to run the offline assertion path.
      ollama_host:       base URL for the local ``ollama`` backend only.
      log:               JSONL path override, default
                         Config.resolve_dir()/sessions/<session-id>.jsonl.
      max_output_tokens: per-reply output cap, default the task's value.
      context_window:    input-capacity override, default the model's catalog
                         window.
      setup:             callable given the RunDSL to register inline tools.
      transport, sleep:  passed to the Client; default the live transport and
                         time.sleep. The offline assertion path injects a stub.
    """
    logger: Logger | None = None
    operator_server: Any = None
    try:
        assembled = _assemble(
            system=system, model=model, backend=backend, api_key=api_key,
            ollama_host=ollama_host, log=log,
            max_iterations=max_iterations,
            max_output_tokens=max_output_tokens, context_window=context_window,
            setup=setup, transport=transport, sleep=sleep,
            objective_context=(
                objective_context or ObjectiveContext.create(task)
            ),
        )
        logger = assembled.logger
        operator_pair = start_operator_control()
        operator = None
        if operator_pair is not None:
            operator, operator_server = operator_pair
        agent = Agent(
            assembled.context, assembled.registry, assembled.builder,
            assembled.client,
            task=Player,
            task_settings=assembled.task_settings,
            max_iterations=assembled.max_iterations,
            max_turn_tokens=assembled.max_turn_tokens,
            max_turn_cost=assembled.max_turn_cost,
            max_output_tokens=assembled.max_output_tokens,
            thinking=thinking,
            logger=logger,
            operator=operator,
            state_block_source=_state_block_source(
                assembled.config, assembled.registry,
            ),
            state_fields_sink=_state_fields_sink(
                assembled.config, assembled.registry,
            ),
            campaign_line_source=_campaign_line_source(
                assembled.config, assembled.registry,
            ),
        )
        logger.turn(n=1, instruction=task)
        assembled.context.add(Message.user(task))
        try:
            return agent.run()
        except OperatorStopped:
            message = "[agent stopped by authenticated operator]"
            assembled.context.add(Message.assistant(message))
            return message
    finally:
        if operator_server is not None:
            operator_server.close()
        if logger is not None:
            logger.close()


def repl(*,
         system: str | None = None,
         model: str | None = None,
         backend: str | None = None,
         api_key: str | None = None,
         ollama_host: str = "http://localhost:11434",
         log: str | None = None,
         max_iterations: int | None = None,
         max_output_tokens: int | None = None,
         thinking: str | None = None,
         context_window: int | None = None,
         setup: Callable[[RunDSL], None] | None = None,
         transport: Transport | None = None,
         sleep: Callable[[float], None] | None = None,
         tui: bool = True,
         input: TextIO | None = None,
         output: TextIO | None = None,
         initial_task: str | None = None,
         objective_context: ObjectiveContext | None = None) -> None:
    """Wire every primitive, then run the interactive session loop.

    Options are identical to :func:`run` minus ``task`` (the user supplies
    tasks interactively), plus injectable ``input``/``output`` streams that
    default to ``sys.stdin``/``sys.stdout``. The streams and the forwarded stub
    ``transport`` are what make an otherwise interactive, live-API loop
    verifiable offline.

    ``tui`` (default true) launches the full-screen Textual front-end wrapping
    the :class:`Repl`. ``tui=False`` runs the plain line-oriented REPL over the
    ``input``/``output`` streams. The loader sets ``tui=False`` for ``--no-tui``.
    ``initial_task`` runs turn one before the plain REPL reads another line.
    Its optional ``objective_context`` is retained beside session-start
    evidence.
    """
    if initial_task is not None and tui:
        raise ValueError("initial_task is supported only by the plain REPL")
    if objective_context is not None and initial_task is None:
        raise ValueError("objective_context requires initial_task")
    logger: Logger | None = None
    operator_server: Any = None
    try:
        assembled = _assemble(
            system=system, model=model, backend=backend, api_key=api_key,
            ollama_host=ollama_host, log=log,
            max_iterations=max_iterations,
            max_output_tokens=max_output_tokens, context_window=context_window,
            setup=setup, transport=transport, sleep=sleep,
            objective_context=objective_context,
        )
        logger = assembled.logger
        operator_pair = start_operator_control()
        operator = None
        if operator_pair is not None:
            operator, operator_server = operator_pair
        session = Repl(
            context=assembled.context,
            registry=assembled.registry,
            builder=assembled.builder,
            client=assembled.client,
            logger=logger,
            task_settings=assembled.task_settings,
            max_iterations=assembled.max_iterations,
            max_turn_tokens=assembled.max_turn_tokens,
            max_output_tokens=assembled.max_output_tokens,
            thinking=thinking,
            config_dir=assembled.config_dir,
            provider=assembled.provider,
            model=assembled.model,
            version=__version__,
            api_key=assembled.backend.api_key,
            servers=assembled.servers,
            operator=operator,
            input=input,
            output=output,
        )
        try:
            if tui:
                # Imported here, not at module load, so the plain REPL and the
                # offline assertion path never pull in Textual unless the TUI is
                # actually launched.
                from .tui import Tui

                Tui(session).run()
            else:
                session.start(initial_task=initial_task)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=session.output)
    finally:
        if operator_server is not None:
            operator_server.close()
        if logger is not None:
            logger.close()
