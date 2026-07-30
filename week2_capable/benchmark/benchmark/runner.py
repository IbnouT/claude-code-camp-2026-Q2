"""Process lifecycle, budget headroom, and attempt isolation."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .config import AttemptConfig, Repository
from .journeys import Journey
from .metrics import AttemptMetrics, measure_attempt


class BudgetError(RuntimeError):
    """A paid attempt would violate its explicit cumulative cap."""


@dataclass(frozen=True)
class SurfaceProof:
    """The stable MCP surface measured before a run."""

    profile_id: str
    advertised_tools: int
    schema_bytes: int
    schema_token_estimate: int
    capability_digest: str
    output: str


@dataclass
class Budget:
    """Cumulative spend with per-attempt headroom."""

    cap: float
    spent: float = 0.0

    def require_headroom(self, max_turn_cost: float) -> None:
        if self.cap <= 0:
            raise BudgetError("the cumulative cap must be positive")
        if max_turn_cost <= 0:
            raise BudgetError("the agent max_turn_cost must be positive")
        if self.spent + max_turn_cost > self.cap:
            raise BudgetError(
                f"remaining cap ${self.cap - self.spent:.4f} is below the "
                f"${max_turn_cost:.4f} per-attempt ceiling"
            )

    def record(self, cost_usd: float | None) -> None:
        if cost_usd is None:
            raise BudgetError("attempt is unpriced, stopping the paid sequence")
        if self.spent + cost_usd > self.cap:
            raise BudgetError("priced result exceeds the cumulative cap")
        self.spent = round(self.spent + cost_usd, 8)


def prove_surface(
    command: Sequence[str] = ("boukensha-gateway",),
    *,
    profile: str = "direct-full",
    environment: Mapping[str, str] | None = None,
) -> SurfaceProof:
    """Run the installed gateway's non-network surface proof."""
    completed = subprocess.run(
        [*command, "--profile", profile, "--prove"],
        env={**os.environ, **(environment or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0 or "SURFACE PROOF: PASS" not in output:
        raise RuntimeError(f"gateway surface proof failed:\n{output}")
    return SurfaceProof(
        profile_id=_field(output, "profile"),
        advertised_tools=int(_field(output, "advertised tools")),
        schema_bytes=int(_field(output, "schema bytes").replace(",", "")),
        schema_token_estimate=(
            int(_field(output, "schema bytes").replace(",", "")) + 3
        ) // 4,
        capability_digest=_field(output, "capability digest"),
        output=output,
    )


def run_attempt(
    *,
    repository: Repository,
    config: AttemptConfig,
    journey: Journey,
    attempt_id: str,
    proof: SurfaceProof,
    environment: Mapping[str, str] | None = None,
    launcher: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> AttemptMetrics:
    """Launch one isolated runtime that resets before its first model call."""
    combined = {**os.environ, **(environment or {}), **config.environment()}
    launch = launcher or _launch_agent
    started = time.monotonic()
    completed = launch(repository=repository, journey=journey, config=config, environment=combined)
    wall_ms = round((time.monotonic() - started) * 1000)
    agent_log, gateway_journal = _runtime_evidence(config)
    error = (
        None if completed.returncode == 0
        else _redact(completed.stderr.strip(), combined)
    )
    return measure_attempt(
        attempt_id=attempt_id,
        journey=journey,
        agent_log=agent_log,
        gateway_journal=gateway_journal,
        wall_ms=wall_ms,
        process_ok=completed.returncode == 0,
        schema_bytes=proof.schema_bytes,
        schema_token_estimate=proof.schema_token_estimate,
        result_mode=config.result_mode,
        reset_id=_reset_id(gateway_journal),
        error=error,
        models_path=repository.agent / "boukensha" / "models.yaml",
    )


def _launch_agent(
    *,
    repository: Repository,
    journey: Journey,
    config: AttemptConfig,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    env = dict(environment)
    return subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repository.agent),
            "boukensha",
            "--task-stdin",
            "--reset-baseline",
            "level1-temple@1",
            "--player-profile",
            config.player_profile,
        ],
        cwd=repository.agent,
        env=env,
        input=journey.order + "\n",
        capture_output=True,
        text=True,
        check=False,
    )


def _runtime_evidence(config: AttemptConfig) -> tuple[Path, Path]:
    registry = config.directory / "registry.db"
    if not registry.is_file():
        return (
            config.directory / "missing-agent.jsonl",
            config.directory / "missing-gateway.db",
        )
    database = sqlite3.connect(registry)
    try:
        row = database.execute(
            """
            SELECT session_dir
            FROM sessions
            WHERE player_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (config.player_profile,),
        ).fetchone()
    finally:
        database.close()
    if row is None:
        return (
            config.directory / "missing-agent.jsonl",
            config.directory / "missing-gateway.db",
        )
    session_dir = Path(str(row[0]))
    return session_dir / "agent.jsonl", session_dir / "gateway.db"


def _reset_id(gateway_journal: Path) -> str | None:
    if not gateway_journal.is_file():
        return None
    database = sqlite3.connect(gateway_journal)
    try:
        row = database.execute(
            """
            SELECT payload
            FROM events
            WHERE kind = 'reset_receipt'
            ORDER BY seq DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        database.close()
    if row is None:
        return None
    try:
        payload = json.loads(str(row[0]))
    except json.JSONDecodeError:
        return None
    value = payload.get("reset_id") if isinstance(payload, dict) else None
    return value if isinstance(value, str) and value else None


def _field(output: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"gateway proof omitted {label!r}")
    return match.group(1)


def _redact(text: str, environment: Mapping[str, str]) -> str:
    redacted = text
    sensitive = ("KEY", "PASSWORD", "SECRET", "TOKEN")
    for name, value in environment.items():
        if value and any(marker in name.upper() for marker in sensitive):
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted
