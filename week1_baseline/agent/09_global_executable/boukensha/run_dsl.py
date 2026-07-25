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

from typing import Any, Callable, NamedTuple, TextIO

from .agent import Agent
from .backends import Backend, backend_for
from .client import Client, Transport
from .config import Config
from .context import Context
from .logger import Logger
from .message import Message
from .prompt_builder import PromptBuilder
from .registry import Registry
from .repl import Repl
from .tasks import Player
from .version import __version__


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
    mud_host: str
    mud_port: int
    mud_username: str | None


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
        mud_host=cfg.mud_host,
        mud_port=cfg.mud_port,
        mud_username=cfg.mud_username,
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
            api_key_override=api_key,
            ollama_host=ollama_host,
            mud_host=assembled.mud_host,
            mud_port=assembled.mud_port,
            mud_username=assembled.mud_username,
            input=input,
            output=output,
        )
        # A real terminal gets history recall and tab completion of commands
        # from stdlib readline. Only in the interactive branch: an injected
        # stream (the offline path) neither needs nor supports it.
        if input is None and output is None:
            _enable_readline(session)
        try:
            session.start()
        except KeyboardInterrupt:
            print("\nInterrupted.", file=session.output)
    finally:
        if logger is not None:
            logger.close()


def _enable_readline(session: Repl) -> None:
    """Wire readline command history and tab completion, best effort."""
    try:
        import readline
    except ImportError:  # pragma: no cover - platform without readline
        return
    names = sorted(session._commands)

    def complete(text: str, state: int) -> str | None:
        matches = [n for n in names if n.startswith(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer(complete)
    readline.parse_and_bind("tab: complete")
