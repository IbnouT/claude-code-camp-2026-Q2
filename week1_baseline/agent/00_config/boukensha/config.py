"""Configuration: the single source of truth for settings and secrets.

Config reads a ``.boukensha/`` directory: ``.env`` for secrets (loaded into
the environment) and ``settings.yaml`` for everything else. The directory is
resolved from ``BOUKENSHA_DIR`` if set, else the nearest ``.boukensha/`` found
walking up from the current directory (like git repo discovery), else
``~/.boukensha``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

#: Default config directory for a real install.
DEFAULT_DIR = Path.home() / ".boukensha"


class ConfigError(Exception):
    """A malformed configuration file, reported with the offending key."""


class Config:
    """Loads and exposes the agent's configuration.

    Resolution order for the config directory:

    1. ``BOUKENSHA_DIR`` environment variable
    2. the nearest existing ``.boukensha/`` walking up from the current
       directory to the filesystem root
    3. ``~/.boukensha``

    A missing ``settings.yaml`` or ``.env`` is not an error; a malformed
    ``settings.yaml`` raises :class:`ConfigError` naming the offending key.
    """

    def __init__(self) -> None:
        self.dir: Path = self._resolve_dir()
        self._load_env()
        self.settings: dict[str, Any] = self._load_settings()

    # -- lookups -----------------------------------------------------------

    def dig(self, *keys: str) -> Any:
        """Fetch a nested value from settings, e.g. ``dig("mud", "host")``."""
        node: Any = self.settings
        for key in keys:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node

    def tasks(self, name: str | None = None) -> Any:
        """All task settings, or one task's settings dict by name."""
        all_tasks = self.dig("tasks") or {}
        return all_tasks.get(name) if name else all_tasks

    # -- paths -------------------------------------------------------------

    @property
    def user_prompts_dir(self) -> Path:
        """The user's prompt-override directory (``<dir>/prompts``)."""
        return self.dir / "prompts"

    def user_prompt_path(self, task_name: str, name: str = "system") -> Path:
        """Where a task's prompt-override file lives (``<dir>/prompts/<task>/<name>.md``)."""
        return self.user_prompts_dir / task_name / f"{name}.md"

    # -- MUD connection ----------------------------------------------------

    @property
    def mud_host(self) -> str:
        return self.dig("mud", "host") or "localhost"

    @property
    def mud_port(self) -> int:
        return int(self.dig("mud", "port") or 4000)

    @property
    def mud_username(self) -> str | None:
        return self.dig("mud", "username")

    @property
    def mud_password(self) -> str | None:
        """The MUD password, a secret read from the environment (.env)."""
        return os.environ.get("MUD_PASSWORD")

    # -- representation ----------------------------------------------------

    def __str__(self) -> str:
        return f"<boukensha.Config dir={self.dir} tasks={','.join(self.tasks())}>"

    __repr__ = __str__

    # -- loading -----------------------------------------------------------

    @staticmethod
    def _resolve_dir() -> Path:
        raw = os.environ.get("BOUKENSHA_DIR")
        if raw:
            return Path(raw).expanduser().resolve()
        cwd = Path.cwd()
        for parent in (cwd, *cwd.parents):
            candidate = parent / ".boukensha"
            if candidate.is_dir():
                return candidate
        return DEFAULT_DIR

    def _load_env(self) -> None:
        env_file = self.dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

    def _load_settings(self) -> dict[str, Any]:
        settings_file = self.dir / "settings.yaml"
        if not settings_file.exists():
            return {}
        loaded = yaml.safe_load(settings_file.read_text()) or {}
        self._validate(loaded)
        return loaded

    @staticmethod
    def _validate(settings: Any) -> None:
        if not isinstance(settings, dict):
            raise ConfigError(
                f"settings.yaml: expected a mapping at the top level, "
                f"got {type(settings).__name__}"
            )
        tasks = settings.get("tasks")
        if tasks is not None and not isinstance(tasks, dict):
            raise ConfigError(
                f"settings.yaml: 'tasks' must be a mapping of task name to "
                f"settings, got {type(tasks).__name__}"
            )
        for name, entry in (tasks or {}).items():
            if not isinstance(entry, dict):
                raise ConfigError(
                    f"settings.yaml: 'tasks.{name}' must be a mapping "
                    f"(provider, model, ...), got {type(entry).__name__}"
                )
