"""Repository paths and isolated agent settings for one attempt."""

from __future__ import annotations

import copy
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values


class BenchmarkConfigError(RuntimeError):
    """The repository cannot supply a safe benchmark configuration."""


_CLI_PLAYER_PROFILE = "benchmark-cli"
_CLI_PLAYER_PASSWORD_ENV = "BOUKENSHA_PLAYER_PASSWORD"
RESULT_MODES = ("raw", "minimal", "full")


@dataclass(frozen=True)
class Repository:
    """Paths shared by every benchmark attempt."""

    root: Path

    @classmethod
    def discover(cls) -> "Repository":
        return cls(Path(__file__).resolve().parents[3])

    @property
    def agent(self) -> Path:
        return self.root / "week2_capable" / "agent"

    @property
    def settings_dir(self) -> Path:
        return self.root / ".boukensha"

    @property
    def week1_sessions(self) -> Path:
        return self.settings_dir / "sessions"

    def player_password(
        self,
        profile_id: str,
        password_env: str,
    ) -> str | None:
        value = os.environ.get(password_env)
        if value:
            return value
        for path in (
            self.settings_dir / "profiles" / profile_id / ".env",
            self.settings_dir / ".env",
        ):
            if not path.is_file():
                continue
            candidate = dotenv_values(path).get(password_env)
            if candidate:
                return candidate
        return None

    def shared_secret(self, name: str) -> str | None:
        value = os.environ.get(name)
        if value:
            return value
        path = self.settings_dir / ".env"
        if not path.is_file():
            return None
        return dotenv_values(path).get(name)


@dataclass(frozen=True)
class AttemptConfig:
    """Public configuration material created for one isolated attempt."""

    directory: Path
    player_profile: str
    player_password_env: str
    admin_password_env: str
    profile: str
    result_mode: str
    max_turn_cost: float

    def environment(self) -> dict[str, str]:
        return {
            "BOUKENSHA_DIR": str(self.directory),
        }


def create_attempt(
    repository: Repository,
    directory: Path,
    *,
    profile: str = "direct-full",
    result_mode: str = "full",
    player_profile: str | None = None,
    player_character: str | None = None,
    model: str | None = None,
    compaction_threshold: float | None = None,
    max_iterations: int | None = None,
    max_turn_cost: float | None = None,
) -> AttemptConfig:
    """Create a secret-free settings overlay for one run."""
    if result_mode not in RESULT_MODES:
        raise BenchmarkConfigError(
            f"result mode must be one of {', '.join(RESULT_MODES)}"
        )
    source = repository.settings_dir / "settings.yaml"
    if not source.is_file():
        raise BenchmarkConfigError(f"missing public settings: {source}")
    loaded = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise BenchmarkConfigError("settings.yaml must contain a mapping")

    settings: dict[str, Any] = copy.deepcopy(loaded)
    servers = settings.setdefault("mcp_servers", {})
    mud = servers.get("mud")
    if not isinstance(mud, dict):
        raise BenchmarkConfigError("settings need mcp_servers.mud")

    directory.mkdir(parents=True, exist_ok=True)
    mud["command"] = "boukensha-gateway"
    mud["args"] = []
    mud["result_mode"] = result_mode
    mud.pop("env", None)

    gateway = settings.setdefault("gateway", {})
    if not isinstance(gateway, dict):
        raise BenchmarkConfigError("settings need a gateway mapping")
    connection = gateway.setdefault("connection", {})
    if not isinstance(connection, dict):
        raise BenchmarkConfigError("settings need gateway.connection")
    selected_profile, password_env = _player_profile(
        gateway,
        player_profile,
        player_character,
    )
    connection["player_profile"] = selected_profile
    admin = gateway.get("admin") or {}
    if not isinstance(admin, dict):
        raise BenchmarkConfigError("settings need gateway.admin")
    admin_password_env = str(
        admin.get("password_env") or "MUD_ADMIN_PASSWORD"
    ).strip()
    if not admin_password_env:
        raise BenchmarkConfigError("gateway.admin.password_env must not be empty")
    surface = gateway.setdefault("surface", {})
    if not isinstance(surface, dict):
        raise BenchmarkConfigError("settings need gateway.surface")
    surface["profile"] = profile
    surface["enable"] = []
    surface["disable"] = []
    surface["allow_raw"] = False

    tasks = settings.get("tasks") or {}
    player = tasks.get("player") or {}
    if model is not None:
        if not model.strip():
            raise BenchmarkConfigError("model must not be empty")
        player["model"] = model
    if compaction_threshold is not None:
        if not 0 < compaction_threshold <= 1:
            raise BenchmarkConfigError(
                "compaction_threshold must be above zero and at most one"
            )
        player["compaction_threshold"] = compaction_threshold
    if max_iterations is not None:
        if max_iterations < 1:
            raise BenchmarkConfigError("max_iterations must be positive")
        player["max_iterations"] = max_iterations
    if max_turn_cost is not None:
        if max_turn_cost <= 0:
            raise BenchmarkConfigError("max_turn_cost must be positive")
        player["max_turn_cost"] = max_turn_cost
    try:
        max_turn_cost = float(player["max_turn_cost"])
    except (KeyError, TypeError, ValueError) as error:
        raise BenchmarkConfigError(
            "tasks.player.max_turn_cost must be priced and positive"
        ) from error
    if max_turn_cost <= 0:
        raise BenchmarkConfigError("max_turn_cost must be positive")

    (directory / "settings.yaml").write_text(
        yaml.safe_dump(settings, sort_keys=False), encoding="utf-8"
    )
    _copy_optional(repository.settings_dir / "models.yaml", directory / "models.yaml")
    prompt_source = repository.settings_dir / "prompts"
    if prompt_source.is_dir():
        shutil.copytree(prompt_source, directory / "prompts", dirs_exist_ok=True)

    return AttemptConfig(
        directory=directory,
        player_profile=selected_profile,
        player_password_env=password_env,
        admin_password_env=admin_password_env,
        profile=profile,
        result_mode=result_mode,
        max_turn_cost=max_turn_cost,
    )


def _player_profile(
    gateway: dict[str, Any],
    requested: str | None,
    player_character: str | None,
) -> tuple[str, str]:
    connection = gateway.get("connection") or {}
    players = gateway.get("players") or {}
    if not isinstance(connection, dict) or not isinstance(players, dict):
        raise BenchmarkConfigError(
            "settings need gateway.connection and gateway.players mappings"
        )
    if requested and player_character:
        raise BenchmarkConfigError(
            "player_profile and player_character are mutually exclusive"
        )
    if player_character is not None:
        character = player_character.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", character):
            raise BenchmarkConfigError(
                "player character must start with a letter and contain only "
                "letters, digits, underscore, or dash"
            )
        players[_CLI_PLAYER_PROFILE] = {
            "character": character,
            "password_env": _CLI_PLAYER_PASSWORD_ENV,
        }
        return _CLI_PLAYER_PROFILE, _CLI_PLAYER_PASSWORD_ENV
    selected = str(
        requested
        or connection.get("player_profile")
        or ""
    ).strip()
    if not selected:
        raise BenchmarkConfigError(
            "gateway.connection.player_profile or --player-profile is required"
        )
    profile = players.get(selected)
    if not isinstance(profile, dict):
        raise BenchmarkConfigError(f"unknown player profile {selected!r}")
    password_env = str(profile.get("password_env") or "MUD_PASSWORD").strip()
    if not password_env:
        raise BenchmarkConfigError(
            f"gateway.players.{selected}.password_env must not be empty"
        )
    return selected, password_env


def _copy_optional(source: Path, target: Path) -> None:
    if source.is_file():
        shutil.copy2(source, target)
