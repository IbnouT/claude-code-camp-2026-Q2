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

import sys
from typing import Any, Callable, NamedTuple, TextIO

from .agent import Agent
from .backends import Backend, backend_for
from .client import Client, Transport
from .config import Config
from .context import Context
from .errors import McpServerError, McpToolCollisionError
from .logger import Logger
from .message import Message
from .prompt_builder import PromptBuilder
from .registry import Registry
from .repl import Repl
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
    max_output_tokens: int | None
    config_dir: str
    provider: str
    model: str
    servers: dict[str, int]


def _assemble(*,
              system: str | None,
              model: str | None,
              backend: str | None,
              api_key: str | None,
              ollama_host: str,
              log: str | None,
              max_iterations: int | None = None,
              max_output_tokens: int | None,
              setup: Callable[[RunDSL], None] | None,
              transport: Transport | None,
              sleep: Callable[[float], None] | None) -> _Assembled:
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
    if model is None:
        model = Player.model(task_settings)
    if backend is None:
        backend = Player.provider(task_settings)

    if max_iterations is None:
        effective_max_iterations = Player.max_iterations(task_settings)
    else:
        effective_max_iterations = max_iterations
    if max_output_tokens is None:
        effective_max_output_tokens = Player.max_output_tokens(task_settings)
    else:
        effective_max_output_tokens = max_output_tokens

    ctx = Context(system)
    registry = Registry()
    # MCP tools are registered before setup, so an inline tool a setup callable
    # adds collides against an MCP tool exactly as two servers would, and both
    # are present when the prompt builder snapshots the toolset below.
    servers = _register_mcp_servers(registry, cfg.mcp_servers())
    if setup is not None:
        setup(RunDSL(registry))

    be = backend_for(backend, model, api_key=api_key)
    be.configure_host(ollama_host)

    builder = PromptBuilder(ctx, be, tuple(registry.tools.values()))
    client = Client(builder, transport=transport, sleep=sleep)
    logger = Logger(log=log, snapshot={
        "task": Player.task_name,
        "system": system,
        "max_iterations": effective_max_iterations,
        "max_output_tokens": effective_max_output_tokens,
        "model": model,
        "provider": backend,
    })

    return _Assembled(
        context=ctx,
        registry=registry,
        builder=builder,
        client=client,
        logger=logger,
        backend=be,
        task_settings=task_settings,
        max_iterations=effective_max_iterations,
        max_output_tokens=effective_max_output_tokens,
        config_dir=str(cfg.dir),
        provider=backend,
        model=model,
        servers=servers,
    )


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
      setup:             callable given the RunDSL to register inline tools.
      transport, sleep:  passed to the Client; default the live transport and
                         time.sleep. The offline assertion path injects a stub.
    """
    logger: Logger | None = None
    try:
        assembled = _assemble(
            system=system, model=model, backend=backend, api_key=api_key,
            ollama_host=ollama_host, log=log,
            max_iterations=max_iterations,
            max_output_tokens=max_output_tokens, setup=setup,
            transport=transport, sleep=sleep,
        )
        logger = assembled.logger
        agent = Agent(
            assembled.context, assembled.registry, assembled.builder,
            assembled.client,
            task=Player,
            task_settings=assembled.task_settings,
            max_iterations=assembled.max_iterations,
            max_output_tokens=assembled.max_output_tokens,
            thinking=thinking,
            logger=logger,
        )
        assembled.context.add(Message.user(task))
        return agent.run()
    finally:
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
         setup: Callable[[RunDSL], None] | None = None,
         transport: Transport | None = None,
         sleep: Callable[[float], None] | None = None,
         input: TextIO | None = None,
         output: TextIO | None = None) -> None:
    """Wire every primitive, then run the interactive session loop.

    Options are identical to :func:`run` minus ``task`` (the user supplies
    tasks interactively), plus injectable ``input``/``output`` streams that
    default to ``sys.stdin``/``sys.stdout``. The streams and the forwarded stub
    ``transport`` are what make an otherwise interactive, live-API loop
    verifiable offline.
    """
    logger: Logger | None = None
    try:
        assembled = _assemble(
            system=system, model=model, backend=backend, api_key=api_key,
            ollama_host=ollama_host, log=log,
            max_iterations=max_iterations,
            max_output_tokens=max_output_tokens, setup=setup,
            transport=transport, sleep=sleep,
        )
        logger = assembled.logger
        session = Repl(
            context=assembled.context,
            registry=assembled.registry,
            builder=assembled.builder,
            client=assembled.client,
            logger=logger,
            task_settings=assembled.task_settings,
            max_iterations=assembled.max_iterations,
            max_output_tokens=assembled.max_output_tokens,
            thinking=thinking,
            config_dir=assembled.config_dir,
            provider=assembled.provider,
            model=assembled.model,
            version=__version__,
            api_key=assembled.backend.api_key,
            servers=assembled.servers,
            input=input,
            output=output,
        )
        try:
            session.start()
        except KeyboardInterrupt:
            print("\nInterrupted.", file=session.output)
    finally:
        if logger is not None:
            logger.close()
