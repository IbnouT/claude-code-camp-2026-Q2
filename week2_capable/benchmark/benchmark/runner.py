"""Process lifecycle, budget headroom, and attempt isolation."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .config import AttemptConfig, Repository
from .journeys import Journey
from .metrics import AttemptMetrics, measure_attempt
from .reset import ResetResult, reset_once


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


_AGENT_LAUNCH = (
    "import os; from boukensha import run; "
    "print(run(os.environ['BOUKENSHA_BENCHMARK_TASK'], "
    "log=os.environ['BOUKENSHA_BENCHMARK_LOG']))"
)


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
    resetter: Callable[..., ResetResult] = reset_once,
    launcher: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> AttemptMetrics:
    """Reset first, then launch exactly one agent turn and measure both logs."""
    combined = {**os.environ, **(environment or {}), **config.environment()}
    try:
        reset_result = resetter(
            socket_path=config.admin_socket,
            journal_path=config.admin_journal,
            environment=combined,
        )
    except Exception as error:
        return measure_attempt(
            attempt_id=attempt_id,
            journey=journey,
            agent_log=config.agent_log,
            gateway_journal=config.gateway_journal,
            wall_ms=0,
            process_ok=False,
            schema_bytes=proof.schema_bytes,
            schema_token_estimate=proof.schema_token_estimate,
            error=_redact(f"reset failed: {error}", combined),
        )

    launch = launcher or _launch_agent
    started = time.monotonic()
    completed = launch(repository=repository, journey=journey, config=config, environment=combined)
    wall_ms = round((time.monotonic() - started) * 1000)
    error = (
        None if completed.returncode == 0
        else _redact(completed.stderr.strip(), combined)
    )
    return measure_attempt(
        attempt_id=attempt_id,
        journey=journey,
        agent_log=config.agent_log,
        gateway_journal=config.gateway_journal,
        wall_ms=wall_ms,
        process_ok=completed.returncode == 0,
        schema_bytes=proof.schema_bytes,
        schema_token_estimate=proof.schema_token_estimate,
        reset_id=reset_result.reset_id,
        error=error,
    )


def _launch_agent(
    *,
    repository: Repository,
    journey: Journey,
    config: AttemptConfig,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    env = {
        **environment,
        "BOUKENSHA_BENCHMARK_TASK": journey.order,
        "BOUKENSHA_BENCHMARK_LOG": str(config.agent_log),
    }
    return subprocess.run(
        ["uv", "run", "--project", str(repository.agent), "python", "-c", _AGENT_LAUNCH],
        cwd=repository.agent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


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
