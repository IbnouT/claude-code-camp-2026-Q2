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

from .errors import ConfigError
from .mcp.transport import DEFAULT_TIMEOUT

#: Default config directory for a real install.
DEFAULT_DIR = Path.home() / ".boukensha"


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
        self.dir: Path = self.resolve_dir()
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

    def agent_setting(self, key: str) -> Any:
        """One value from the top-level ``agent:`` block, or ``None``.

        The agent-wide circuit breakers (``max_iterations``,
        ``max_output_tokens``, ``max_turn_tokens``, ``compaction_threshold``)
        live here (decision A4a). A task may still override any of them under
        ``tasks.<name>.*``, so this is the middle layer: task value, then this
        agent default, then the code default.
        """
        return self.dig("agent", key)

    def mcp_servers(self) -> dict[str, dict[str, Any]]:
        """The ``mcp_servers:`` block, keyed by name, with defaults applied.

        This is where every one of the agent's tools comes from: boukensha
        ships none of its own. Each entry resolves to
        ``{command, args, env, prefix, required}``:

        - ``command``: stringified, default ``""``.
        - ``args``: list of strings, default ``[]``.
        - ``env``: string->string dict, default ``{}`` (values stringified, so a
          YAML integer port survives into the spawn environment).
        - ``prefix``: string or ``None``, default ``None``.
        - ``required``: bool, default ``True``. ``required: false`` lets a server
          fail to spawn without taking the agent down.
        - ``timeout``: per-call ceiling in seconds, default ``DEFAULT_TIMEOUT``,
          so one hung tool call cannot hang the agent.
        - ``allow``: list of the server's tool names to register, or ``None`` for
          all. ``deny``: list of names to exclude, default ``[]``. Together they
          express a constrained (for example read-only) variant as config.

        An absent block yields ``{}``. A bare ``name:`` (no body) means all
        defaults. Malformed entries are rejected at load time by
        :meth:`_validate_mcp_servers`, so the coercion here is safe.
        """
        raw_block = self.dig("mcp_servers") or {}
        out: dict[str, dict[str, Any]] = {}
        for name, raw in raw_block.items():
            entry = raw if isinstance(raw, dict) else {}
            env = entry.get("env") or {}
            required = entry.get("required")
            timeout = entry.get("timeout")
            allow = entry.get("allow")
            out[str(name)] = {
                "command": str(entry.get("command") or ""),
                "args": [str(a) for a in (entry.get("args") or [])],
                "env": {str(k): str(v) for k, v in env.items()},
                "prefix": None if entry.get("prefix") is None else str(entry.get("prefix")),
                "required": True if required is None else bool(required),
                "timeout": DEFAULT_TIMEOUT if timeout is None else float(timeout),
                "allow": None if allow is None else [str(a) for a in allow],
                "deny": [str(d) for d in (entry.get("deny") or [])],
            }
        return out

    # -- paths -------------------------------------------------------------

    @property
    def user_prompts_dir(self) -> Path:
        """The user's prompt-override directory (``<dir>/prompts``)."""
        return self.dir / "prompts"

    def user_prompt_path(self, task_name: str, name: str = "system") -> Path:
        """Where a task's prompt-override file lives (``<dir>/prompts/<task>/<name>.md``)."""
        return self.user_prompts_dir / task_name / f"{name}.md"

    @property
    def user_models_path(self) -> Path:
        """The user's model-catalog override file (``<dir>/models.yaml``)."""
        return self.dir / "models.yaml"

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
    def resolve_dir() -> Path:
        """The config directory, resolved without loading anything from it.

        ``BOUKENSHA_DIR`` if set, else the nearest existing ``.boukensha/``
        walking up from the current directory, else ``~/.boukensha``. The one
        resolver every component uses, so they can never disagree on the
        directory.
        """
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
        Config._validate_mcp_servers(settings.get("mcp_servers"))

    @staticmethod
    def _validate_mcp_servers(block: Any) -> None:
        """Reject malformed ``mcp_servers`` shapes at load, naming the field.

        A misshapen entry (``args`` as a bare string, ``env`` as a list) would
        otherwise mangle silently or raise an unrelated error deep in spawn, so
        it is caught here in the same voice as the ``tasks`` validation above.
        """
        if block is None:
            return
        if not isinstance(block, dict):
            raise ConfigError(
                f"settings.yaml: 'mcp_servers' must be a mapping of server name "
                f"to settings, got {type(block).__name__}"
            )
        for name, entry in block.items():
            if entry is None:
                continue  # a bare `name:` means "all defaults".
            if not isinstance(entry, dict):
                raise ConfigError(
                    f"settings.yaml: 'mcp_servers.{name}' must be a mapping "
                    f"(command, args, ...), got {type(entry).__name__}"
                )
            for field in ("command", "prefix"):
                if field in entry and isinstance(entry[field], (list, dict)):
                    raise ConfigError(
                        f"settings.yaml: 'mcp_servers.{name}.{field}' must be a "
                        f"string, got {type(entry[field]).__name__}"
                    )
            for field in ("args", "allow", "deny"):
                if entry.get(field) is not None and not isinstance(entry[field], list):
                    raise ConfigError(
                        f"settings.yaml: 'mcp_servers.{name}.{field}' must be a "
                        f"list, got {type(entry[field]).__name__}"
                    )
            if entry.get("env") is not None and not isinstance(entry["env"], dict):
                raise ConfigError(
                    f"settings.yaml: 'mcp_servers.{name}.env' must be a mapping, "
                    f"got {type(entry['env']).__name__}"
                )
            if entry.get("timeout") is not None:
                try:
                    value = float(entry["timeout"])
                except (TypeError, ValueError):
                    raise ConfigError(
                        f"settings.yaml: 'mcp_servers.{name}.timeout' must be a "
                        f"number, got {entry['timeout']!r}"
                    ) from None
                if value <= 0:
                    raise ConfigError(
                        f"settings.yaml: 'mcp_servers.{name}.timeout' must be "
                        f"positive, got {value:g}"
                    )
