"""The run DSL: one entry point that hides every primitive.

``run(task=..., setup=...)`` resolves configuration, builds the whole chain
(Context, Registry, backend, PromptBuilder, Client, Logger, Agent), seeds the
task as the first user message, runs one turn, and returns the final text.
Every prior step required assembling that chain by hand; this reduces it to
describing what to do.

``RunDSL`` is the small host handed to ``setup``. It exposes exactly one public
method, ``tool``, so a caller registers ad-hoc tools inline without reaching
the registry, context, or backend behind it.
"""

from __future__ import annotations

from typing import Any, Callable

from .agent import Agent
from .backends import backend_for
from .client import Client, Transport
from .config import Config
from .context import Context
from .logger import Logger
from .message import Message
from .prompt_builder import PromptBuilder
from .registry import Registry
from .tasks import Player


class RunDSL:
    """The host passed to a ``run`` setup callable.

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
      max_iterations:    per-turn iteration ceiling, default the task's value.
      max_output_tokens: per-reply output cap, default the task's value.
      thinking:          reasoning-effort level override, default the task's
                         value. Resolved explicit > task setting, symmetric with
                         the two caps above.
      setup:             callable given the RunDSL to register inline tools.
      transport, sleep:  passed to the Client; default the live transport and
                         time.sleep. The offline assertion path injects a stub.
    """
    logger: Logger | None = None
    try:
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
            "max_iterations": effective_max_iterations,
            "max_output_tokens": effective_max_output_tokens,
            "model": model,
            "provider": backend,
        })
        agent = Agent(
            ctx, registry, builder, client,
            task=Player,
            task_settings=task_settings,
            max_iterations=effective_max_iterations,
            max_output_tokens=effective_max_output_tokens,
            thinking=thinking,
            logger=logger,
        )

        ctx.add(Message.user(task))
        return agent.run()
    finally:
        if logger is not None:
            logger.close()
