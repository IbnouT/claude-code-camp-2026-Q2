"""Repository paths and isolated agent settings for one attempt."""

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class BenchmarkConfigError(RuntimeError):
    """The repository cannot supply a safe benchmark configuration."""


_UNIX_SOCKET_PATH_LIMIT = 103


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


@dataclass(frozen=True)
class AttemptConfig:
    """Public configuration material created for one isolated attempt."""

    directory: Path
    agent_log: Path
    gateway_journal: Path
    admin_journal: Path
    admin_socket: Path
    profile: str
    max_turn_cost: float

    def environment(self) -> dict[str, str]:
        return {
            "BOUKENSHA_DIR": str(self.directory),
            "BOUKENSHA_BENCHMARK_LOG": str(self.agent_log),
            "GATEWAY_JOURNAL": str(self.gateway_journal),
        }


def create_attempt(
    repository: Repository,
    directory: Path,
    *,
    profile: str = "direct-full",
) -> AttemptConfig:
    """Create a secret-free settings overlay for one run."""
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
    gateway_journal = directory / "gateway.db"
    mud["command"] = "boukensha-gateway"
    mud["args"] = ["--profile", profile]
    environment = mud.setdefault("env", {})
    if not isinstance(environment, dict):
        raise BenchmarkConfigError("mcp_servers.mud.env must be a mapping")
    environment["GATEWAY_JOURNAL"] = str(gateway_journal)

    tasks = settings.get("tasks") or {}
    player = tasks.get("player") or {}
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
        agent_log=directory / "agent.jsonl",
        gateway_journal=gateway_journal,
        admin_journal=directory / "admin.db",
        admin_socket=_short_socket_path(directory),
        profile=profile,
        max_turn_cost=max_turn_cost,
    )


def _copy_optional(source: Path, target: Path) -> None:
    if source.is_file():
        shutil.copy2(source, target)


def _short_socket_path(directory: Path) -> Path:
    """Return a stable socket path below the portable Unix path limit."""
    digest = hashlib.sha256(os.fsencode(directory.resolve())).hexdigest()[:16]
    filename = f"boukensha-{digest}.sock"
    candidate = Path(tempfile.gettempdir()) / filename
    if len(os.fsencode(candidate)) <= _UNIX_SOCKET_PATH_LIMIT:
        return candidate
    return Path("/tmp") / filename
