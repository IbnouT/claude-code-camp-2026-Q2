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
from dotenv import dotenv_values, load_dotenv

from .errors import ConfigError
from .mcp.transport import DEFAULT_TIMEOUT

# The five week 3 capabilities. Each has exactly one master flag; every
# number a capability needs is a setting under its block, never a flag.
CAPABILITIES = (
    "knowledge",
    "navigation",
    "survival",
    "economy",
    "campaign",
)
from .tool_result import RESULT_MODES, result_mode

#: Default config directory for a real install.
DEFAULT_DIR = Path.home() / ".boukensha"
GATEWAY_RUNTIME_ENV = frozenset({
    "BOUKENSHA_AGENT_ID",
    "BOUKENSHA_ADMIN_SECRET_FILE",
    "BOUKENSHA_CONTROL_SOCKET",
    "BOUKENSHA_DIR",
    "BOUKENSHA_EXPERIMENT_ID",
    "BOUKENSHA_GATEWAY_SESSION_ID",
    "BOUKENSHA_PLAYER_ID",
    "BOUKENSHA_RUN_ID",
    "BOUKENSHA_SESSION_DIR",
    "BOUKENSHA_SESSION_ID",
})


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
        self._process_environment = dict(os.environ)
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

    def capability(self, name: str) -> bool:
        """Whether one week 3 capability is enabled. Off by default.

        The five capabilities (``CAPABILITIES``) each carry one master flag
        under the top-level ``capabilities:`` block:

        .. code-block:: yaml

            capabilities:
              navigation:
                enabled: true

        Any threshold or bound a capability needs lives as a sibling of
        ``enabled`` under the same block. An unknown name raises
        :class:`ConfigError` so a misspelt flag cannot silently measure
        nothing.
        """
        if name not in CAPABILITIES:
            raise ConfigError(f"unknown capability {name!r}")
        return bool(self.dig("capabilities", name, "enabled"))

    def capability_settings(self, name: str) -> dict[str, Any]:
        """One capability's settings block, ``{}`` when absent."""
        if name not in CAPABILITIES:
            raise ConfigError(f"unknown capability {name!r}")
        block = self.dig("capabilities", name)
        return dict(block) if isinstance(block, dict) else {}

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
            resolved_env = {str(k): str(v) for k, v in env.items()}
            resolved_env.setdefault("BOUKENSHA_DIR", str(self.dir))
            command = str(entry.get("command") or "")
            is_gateway = Path(command).name == "boukensha-gateway"
            if is_gateway:
                for key, value in os.environ.items():
                    if key in GATEWAY_RUNTIME_ENV:
                        resolved_env.setdefault(key, value)
                profile = self.mud_profile()
                password_name = str(
                    profile.get("password_env") or "MUD_PASSWORD"
                )
                password = self.secret(
                    password_name,
                    profile_id=self.mud_player_profile,
                )
                if password:
                    resolved_env.setdefault(password_name, password)
            required = entry.get("required")
            timeout = entry.get("timeout")
            allow = entry.get("allow")
            out[str(name)] = {
                "command": command,
                "args": [str(a) for a in (entry.get("args") or [])],
                "env": resolved_env,
                "prefix": None if entry.get("prefix") is None else str(entry.get("prefix")),
                "required": True if required is None else bool(required),
                "timeout": DEFAULT_TIMEOUT if timeout is None else float(timeout),
                "allow": None if allow is None else [str(a) for a in allow],
                "deny": [str(d) for d in (entry.get("deny") or [])],
                "result_mode": result_mode(str(entry.get("result_mode") or "full")),
                "inherit_env": not is_gateway,
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
        return (
            self.dig("gateway", "connection", "host")
            or self.dig("mud", "host")
            or "localhost"
        )

    @property
    def mud_port(self) -> int:
        return int(
            self.dig("gateway", "connection", "port")
            or self.dig("mud", "port")
            or 4000
        )

    @property
    def mud_username(self) -> str | None:
        profile = self.mud_profile()
        return (
            profile.get("character")
            or self.dig("mud", "username")
        )

    @property
    def mud_password(self) -> str | None:
        """Resolve the selected profile secret without changing the process."""
        profile = self.mud_profile()
        name = str(profile.get("password_env") or "MUD_PASSWORD")
        return self.secret(name, profile_id=self.mud_player_profile)

    @property
    def mud_player_profile(self) -> str:
        return str(
            os.environ.get("BOUKENSHA_PLAYER_ID")
            or os.environ.get("BOUKENSHA_PLAYER_PROFILE")
            or self.dig("gateway", "connection", "player_profile")
            or "default"
        )

    def mud_profile(self, profile_id: str | None = None) -> dict[str, Any]:
        """Return one configured public player profile."""
        profiles = self.dig("gateway", "players") or {}
        selected_id = profile_id or self.mud_player_profile
        selected = profiles.get(selected_id) or {}
        return selected if isinstance(selected, dict) else {}

    def secret(self, name: str, *, profile_id: str | None = None) -> str | None:
        """Resolve one named secret without exposing unrelated values."""
        value = self._process_environment.get(name) or os.environ.get(name)
        if value:
            return value
        paths = []
        if profile_id:
            paths.append(self.dir / "profiles" / profile_id / ".env")
        paths.append(self.dir / ".env")
        for path in paths:
            if not path.is_file():
                continue
            candidate = dotenv_values(path).get(name)
            if candidate:
                return candidate
        return None

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
        if os.environ.get("BOUKENSHA_SESSION_ID"):
            return
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
            mode = entry.get("result_mode")
            if mode is not None and mode not in RESULT_MODES:
                raise ConfigError(
                    f"settings.yaml: 'mcp_servers.{name}.result_mode' must be "
                    f"one of {', '.join(RESULT_MODES)}, got {mode!r}"
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
