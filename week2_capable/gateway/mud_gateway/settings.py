"""Gateway configuration from the shared ``.boukensha`` directory."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml
from dotenv import dotenv_values

from .profiles import PROFILES, Profile, ProfileError, load_profile


class GatewaySettingsError(ValueError):
    """The gateway section in ``settings.yaml`` is malformed."""


# The five week 3 capabilities, mirrored from the agent package. Each has
# exactly one master flag under the top-level ``capabilities:`` block, and
# every number a capability needs is a setting under its block.
CAPABILITIES = (
    "knowledge",
    "navigation",
    "survival",
    "economy",
    "campaign",
)


@dataclass(frozen=True)
class PlayerProfile:
    """One public player identity and the name of its secret."""

    id: str
    character: str
    password_env: str


@dataclass(frozen=True)
class GatewaySettings:
    """Resolved non-secret gateway settings and secret accessors."""

    config_dir: Path
    host: str = "localhost"
    port: int = 4000
    player_profile: str = "default"
    players: Mapping[str, PlayerProfile] = field(default_factory=lambda: {
        "default": PlayerProfile("default", "poucet", "MUD_PASSWORD")
    })
    journal: Path = Path(".boukensha/gateway/gateway.db")
    profile: str = "direct-full"
    enable: frozenset[str] = frozenset()
    disable: frozenset[str] = frozenset()
    allow_raw: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    admin_character: str = "admin"
    admin_password_env: str = "MUD_ADMIN_PASSWORD"
    reset_pause_timeout: float = 15.0
    reset_child_timeout: float = 30.0
    reset_client_timeout: float = 45.0
    capabilities: Mapping[str, bool] = field(default_factory=lambda: {
        name: False for name in CAPABILITIES
    })
    capability_settings: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    agent_id: str | None = None
    session_id: str | None = None
    gateway_session_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None
    session_dir: Path | None = None
    control_socket: Path | None = None

    @classmethod
    def load(cls) -> "GatewaySettings":
        config_dir = _config_dir()
        configured = _load(config_dir / "settings.yaml")
        flags, capability_blocks = _capabilities(config_dir / "settings.yaml")
        connection = _mapping(configured, "connection")
        players = _players(configured.get("players"))
        surface = _mapping(configured, "surface")
        api = _mapping(configured, "api")
        admin = _mapping(configured, "admin")
        reset = _mapping(configured, "reset")
        root = config_dir.parent
        selected = _profile_id(
            os.environ.get("BOUKENSHA_PLAYER_ID")
            or connection.get("player_profile"),
            default="default",
            label="gateway.connection.player_profile",
        )
        if selected not in players:
            raise GatewaySettingsError(
                "gateway.connection.player_profile names an unknown profile "
                f"{selected!r}"
            )
        admin_password_env = _environment_name(
            admin.get("password_env"),
            "MUD_ADMIN_PASSWORD",
            "gateway.admin.password_env",
        )
        if admin_password_env in {
            profile.password_env for profile in players.values()
        }:
            raise GatewaySettingsError(
                "gateway.admin.password_env must differ from every player secret"
            )
        return cls(
            config_dir=config_dir,
            host=_string(connection.get("host"), "localhost"),
            port=_port(connection.get("port"), 4000, "gateway.connection.port"),
            player_profile=selected,
            players=players,
            journal=_runtime_journal(configured, root),
            profile=_profile(surface.get("profile", "direct-full")),
            enable=_names(surface.get("enable", ()), "gateway.surface.enable"),
            disable=_names(surface.get("disable", ()), "gateway.surface.disable"),
            allow_raw=_boolean(
                surface.get("allow_raw", False),
                "gateway.surface.allow_raw",
            ),
            api_host=_string(api.get("host"), "127.0.0.1"),
            api_port=_port(api.get("port"), 8765, "gateway.api.port"),
            admin_character=_string(admin.get("character"), "admin"),
            admin_password_env=admin_password_env,
            reset_pause_timeout=_positive_float(
                reset.get("pause_timeout_seconds"),
                15.0,
                "gateway.reset.pause_timeout_seconds",
            ),
            reset_child_timeout=_positive_float(
                reset.get("child_timeout_seconds"),
                30.0,
                "gateway.reset.child_timeout_seconds",
            ),
            reset_client_timeout=_positive_float(
                reset.get("client_timeout_seconds"),
                45.0,
                "gateway.reset.client_timeout_seconds",
            ),
            capabilities=flags,
            capability_settings=capability_blocks,
            agent_id=os.environ.get("BOUKENSHA_AGENT_ID"),
            session_id=os.environ.get("BOUKENSHA_SESSION_ID"),
            gateway_session_id=os.environ.get("BOUKENSHA_GATEWAY_SESSION_ID"),
            experiment_id=os.environ.get("BOUKENSHA_EXPERIMENT_ID"),
            run_id=os.environ.get("BOUKENSHA_RUN_ID"),
            session_dir=_environment_path("BOUKENSHA_SESSION_DIR"),
            control_socket=_environment_path("BOUKENSHA_CONTROL_SOCKET"),
        )

    @property
    def character(self) -> str:
        return self.player().character

    @property
    def password(self) -> str | None:
        return self.player_password()

    @property
    def admin_password(self) -> str | None:
        if self.session_id:
            return _secret(self.admin_password_env, os.environ)
        return _secret(
            self.admin_password_env,
            os.environ,
            self.config_dir / ".env",
        )

    def player(self, profile_id: str | None = None) -> PlayerProfile:
        selected = self.player_profile if profile_id is None else profile_id
        try:
            return self.players[selected]
        except KeyError as error:
            raise GatewaySettingsError(
                f"unknown player profile {selected!r}"
            ) from error

    def player_password(self, profile_id: str | None = None) -> str | None:
        profile = self.player(profile_id)
        return _secret(
            profile.password_env,
            os.environ,
            self.config_dir / "profiles" / profile.id / ".env",
            self.config_dir / ".env",
        )

    @property
    def player_password_envs(self) -> frozenset[str]:
        return frozenset(profile.password_env for profile in self.players.values())

    def effective_profile(self) -> Profile:
        base = load_profile(self.profile)
        allowed = (base.allowed | self.enable) - self.disable
        if self.allow_raw:
            allowed |= {"send_raw"}
        else:
            allowed -= {"send_raw"}
        if allowed == base.allowed:
            return base
        return load_profile(self.profile, allowed)


def _config_dir() -> Path:
    explicit = os.environ.get("BOUKENSHA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".boukensha"
        if candidate.is_dir():
            return candidate
    return Path.home() / ".boukensha"


def _environment_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return None if not value else Path(value).expanduser().resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise GatewaySettingsError(f"{path}: expected a mapping")
    configured = loaded.get("gateway") or {}
    if not isinstance(configured, dict):
        raise GatewaySettingsError("settings.yaml: 'gateway' must be a mapping")
    _known(
        configured,
        {"connection", "players", "journal", "surface", "api", "admin", "reset"},
        "gateway",
    )
    sections = {
        "connection": {"host", "port", "player_profile"},
        "surface": {"profile", "enable", "disable", "allow_raw"},
        "api": {"host", "port"},
        "admin": {"character", "password_env"},
        "reset": {
            "pause_timeout_seconds",
            "child_timeout_seconds",
            "client_timeout_seconds",
        },
    }
    for name, keys in sections.items():
        _known(_mapping(configured, name), keys, f"gateway.{name}")
    return configured


def _capabilities(
    path: Path,
) -> tuple[dict[str, bool], dict[str, dict[str, Any]]]:
    """Top-level ``capabilities:`` flags and blocks, all off when absent."""
    flags = {name: False for name in CAPABILITIES}
    blocks: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return flags, blocks
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return flags, blocks
    section = loaded.get("capabilities") or {}
    if not isinstance(section, dict):
        raise GatewaySettingsError(
            "settings.yaml: 'capabilities' must be a mapping"
        )
    _known(section, set(CAPABILITIES), "capabilities")
    for name, block in section.items():
        if block is None:
            continue
        if not isinstance(block, dict):
            raise GatewaySettingsError(
                f"settings.yaml: 'capabilities.{name}' must be a mapping"
            )
        flags[name] = _boolean(
            block.get("enabled", False),
            f"capabilities.{name}.enabled",
        )
        blocks[name] = dict(block)
    return flags, blocks


def _players(value: Any) -> dict[str, PlayerProfile]:
    if value is None:
        return {
            "default": PlayerProfile(
                id="default",
                character="poucet",
                password_env="MUD_PASSWORD",
            )
        }
    if not isinstance(value, dict) or not value:
        raise GatewaySettingsError(
            "settings.yaml: 'gateway.players' must be a non-empty mapping"
        )
    profiles: dict[str, PlayerProfile] = {}
    for raw_id, raw_profile in value.items():
        profile_id = _profile_id(
            raw_id,
            default="",
            label="gateway.players profile id",
        )
        if not isinstance(raw_profile, dict):
            raise GatewaySettingsError(
                f"settings.yaml: 'gateway.players.{profile_id}' must be a mapping"
            )
        _known(
            raw_profile,
            {"character", "password_env"},
            f"gateway.players.{profile_id}",
        )
        profiles[profile_id] = PlayerProfile(
            id=profile_id,
            character=_string(raw_profile.get("character"), profile_id),
            password_env=_environment_name(
                raw_profile.get("password_env"),
                "MUD_PASSWORD",
                f"gateway.players.{profile_id}.password_env",
            ),
        )
    return profiles


def _mapping(configured: dict[str, Any], name: str) -> dict[str, Any]:
    value = configured.get(name) or {}
    if not isinstance(value, dict):
        raise GatewaySettingsError(
            f"settings.yaml: 'gateway.{name}' must be a mapping"
        )
    return value


def _known(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise GatewaySettingsError(
            f"settings.yaml: '{label}' has unknown keys {sorted(unknown)}"
        )


def _string(value: Any, default: str) -> str:
    text = default if value is None else str(value).strip()
    if not text:
        raise GatewaySettingsError("gateway string values must not be empty")
    return text


def _port(value: Any, default: int, label: str) -> int:
    try:
        port = default if value is None else int(value)
    except (TypeError, ValueError) as error:
        raise GatewaySettingsError(f"{label} must be an integer") from error
    if not 1 <= port <= 65535:
        raise GatewaySettingsError(f"{label} must be between 1 and 65535")
    return port


def _positive_float(value: Any, default: float, label: str) -> float:
    try:
        number = default if value is None else float(value)
    except (TypeError, ValueError) as error:
        raise GatewaySettingsError(f"{label} must be a number") from error
    if number <= 0:
        raise GatewaySettingsError(f"{label} must be positive")
    return number


def _path(value: Any, root: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else root / path


def _runtime_journal(configured: dict[str, Any], root: Path) -> Path:
    session_dir = os.environ.get("BOUKENSHA_SESSION_DIR")
    if session_dir:
        return Path(session_dir) / "gateway.db"
    return _path(
        configured.get("journal", ".boukensha/gateway/gateway.db"),
        root,
    )


def _profile(value: Any) -> str:
    name = str(value)
    if name not in PROFILES:
        raise GatewaySettingsError(
            f"gateway.surface.profile must be one of {sorted(PROFILES)}"
        )
    return name


def _names(value: Any, label: str) -> frozenset[str]:
    if not isinstance(value, (list, tuple)):
        raise GatewaySettingsError(f"{label} must be a list")
    names = frozenset(str(name).strip() for name in value if str(name).strip())
    if "send_raw" in names:
        raise GatewaySettingsError(
            f"{label} must not contain send_raw, use gateway.surface.allow_raw"
        )
    try:
        load_profile("direct-full", names)
    except ProfileError as error:
        raise GatewaySettingsError(f"{label}: {error}") from error
    return names


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise GatewaySettingsError(f"{label} must be true or false")
    return value


def _profile_id(value: Any, *, default: str, label: str) -> str:
    profile_id = default if value is None else str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", profile_id):
        raise GatewaySettingsError(
            f"{label} must contain only letters, digits, dot, underscore, or dash"
        )
    return profile_id


def _environment_name(value: Any, default: str, label: str) -> str:
    name = default if value is None else str(value).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise GatewaySettingsError(f"{label} must be an environment variable name")
    return name


def _secret(
    name: str,
    environment: Mapping[str, str],
    *files: Path,
) -> str | None:
    value = environment.get(name)
    if value:
        return value
    for path in files:
        if not path.is_file():
            continue
        loaded = dotenv_values(path)
        candidate = loaded.get(name)
        if candidate:
            return candidate
    return None
