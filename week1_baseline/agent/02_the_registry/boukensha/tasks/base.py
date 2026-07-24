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

    @staticmethod
    def _read(path: Path | Traversable) -> str | None:
        return path.read_text().strip() if path.is_file() else None
