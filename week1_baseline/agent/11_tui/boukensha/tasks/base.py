"""Tasks: a role in the agent bound to its own model.

A task's behaviour is expressed as class methods over its settings dict, no
instances. Concrete tasks set :attr:`task_name`.
"""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, ClassVar

from ..errors import ConfigError
from ..models import THINKING_LEVELS

#: Default prompts shipped inside this package (``boukensha/tasks/prompts``).
DEFAULT_PROMPTS = files("boukensha.tasks") / "prompts"


class Task:
    """Stateless resolution of a task's provider, model, and prompts."""

    task_name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Fail at definition time if a concrete task forgets its name.
        super().__init_subclass__(**kwargs)
        if not cls.task_name:
            raise TypeError(f"{cls.__name__} must set task_name")

    # -- required settings -------------------------------------------------

    @classmethod
    def provider(cls, settings: dict[str, Any] | None) -> str:
        value = cls._fetch(settings, "provider")
        if not value:
            raise ConfigError(
                f"tasks.{cls.task_name}.provider is required in settings.yaml"
            )
        return value

    @classmethod
    def model(cls, settings: dict[str, Any] | None) -> str:
        value = cls._fetch(settings, "model")
        if not value:
            raise ConfigError(
                f"tasks.{cls.task_name}.model is required in settings.yaml"
            )
        return value

    # -- optional settings -------------------------------------------------

    @classmethod
    def thinking(cls, settings: dict[str, Any] | None) -> str | None:
        """The task's thinking level, or None when unset."""
        value = cls._fetch(settings, "thinking")
        if value is None:
            return None
        if value not in THINKING_LEVELS:
            raise ConfigError(
                f"tasks.{cls.task_name}.thinking must be one of "
                f"{', '.join(THINKING_LEVELS)}, got {value!r}"
            )
        return value

    #: Turn ceiling default when a task's settings name none.
    DEFAULT_MAX_ITERATIONS: ClassVar[int] = 25
    #: Per-call output token default when a task's settings name none.
    DEFAULT_MAX_OUTPUT_TOKENS: ClassVar[int] = 1024

    @classmethod
    def max_iterations(cls, settings: dict[str, Any] | None) -> int:
        """The turn ceiling, ``int``-coerced, default 25."""
        return cls._integer(settings, "max_iterations", cls.DEFAULT_MAX_ITERATIONS)

    @classmethod
    def max_output_tokens(cls, settings: dict[str, Any] | None) -> int:
        """The per-call output token cap, ``int``-coerced, default 1024."""
        return cls._integer(settings, "max_output_tokens",
                            cls.DEFAULT_MAX_OUTPUT_TOKENS)

    # -- prompt resolution -------------------------------------------------

    @classmethod
    def prompt_override(cls, settings: dict[str, Any] | None,
                        prompt: str = "system") -> bool:
        node = cls._fetch(settings, "prompt_override")
        return isinstance(node, dict) and node.get(prompt) is True

    @classmethod
    def system_prompt(cls, settings: dict[str, Any] | None,
                      override_path: Path | None = None) -> str | None:
        """The task's system prompt: user override first, else the default.

        1. ``override_path`` (from ``Config.user_prompt_path``), when the
           task's ``prompt_override.system`` is true and the file exists.
        2. ``prompts/system.md`` shipped inside this package.
        """
        if override_path is not None and cls.prompt_override(settings, "system"):
            text = cls._read(override_path)
            if text:
                return text
        return cls._read(DEFAULT_PROMPTS / "system.md")

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _fetch(settings: dict[str, Any] | None, key: str) -> Any:
        return settings.get(key) if isinstance(settings, dict) else None

    @classmethod
    def _integer(cls, settings: dict[str, Any] | None, key: str,
                 default: int) -> int:
        value = cls._fetch(settings, key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"tasks.{cls.task_name}.{key} must be an integer, got {value!r}"
            ) from exc

    @staticmethod
    def _read(path: Path | Traversable) -> str | None:
        return path.read_text().strip() if path.is_file() else None
