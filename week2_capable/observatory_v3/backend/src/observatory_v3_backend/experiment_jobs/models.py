"""Typed durable experiment state."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from ..contracts import ExperimentDefinition

ExperimentJobState = Literal[
    "queued",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "cancelled",
]
ExperimentSampleState = Literal[
    "queued",
    "launching",
    "running",
    "success",
    "agent_failure",
    "setup_failure",
    "cancelled",
    "interrupted",
    "excluded",
]

TERMINAL_SAMPLE_STATES = frozenset(
    {
        "success",
        "agent_failure",
        "setup_failure",
        "cancelled",
        "interrupted",
        "excluded",
    }
)


@dataclass(frozen=True, slots=True)
class SampleResult:
    """One retained runner outcome, without inferred session evidence."""

    state: ExperimentSampleState
    detail: str
    cost_usd: float | None = None
    turns: int | None = None
    calls: int | None = None

    def __post_init__(self) -> None:
        if self.state not in TERMINAL_SAMPLE_STATES:
            raise ValueError("sample result state must be terminal")
        for name, value in (
            ("cost_usd", self.cost_usd),
            ("turns", self.turns),
            ("calls", self.calls),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be nonnegative")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")


@dataclass(slots=True)
class ExperimentSample:
    """One stable queue member and its retained outcome."""

    id: str
    arm_id: str
    ordinal: int
    queue_position: int
    state: ExperimentSampleState
    effective_config: dict[str, bool | int | float | str]
    run_id: str | None = None
    session_id: str | None = None
    cost_usd: float | None = None
    turns: int | None = None
    calls: int | None = None
    detail: str = "Waiting for execution"
    started_at: str | None = None
    finished_at: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "arm_id": self.arm_id,
            "ordinal": self.ordinal,
            "queue_position": self.queue_position,
            "state": self.state,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cost_usd": self.cost_usd,
            "turns": self.turns,
            "calls": self.calls,
            "detail": self.detail,
            "effective_config": self.effective_config,
        }


@dataclass(slots=True)
class ExperimentJob:
    """One durable execution request and its immutable queue."""

    id: str
    request_id: str
    player_profile: str
    definition: ExperimentDefinition
    confirmed_max_spend_usd: float
    state: ExperimentJobState = "queued"
    spent_usd: float = 0.0
    current_sample: str | None = None
    stop_requested: bool = False
    launch_blocked: bool = False
    terminal_reason: str | None = None
    concurrency: int = 1
    created_at: str = ""
    updated_at: str = ""
    samples: dict[str, ExperimentSample] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "player_profile": self.player_profile,
            "definition_id": self.definition.id,
            "definition_version": self.definition.version,
            "definition": self.definition.model_dump(mode="json"),
            "state": self.state,
            "confirmed_max_spend_usd": self.confirmed_max_spend_usd,
            "spent_usd": self.spent_usd,
            "current_sample": self.current_sample,
            "launch_blocked": self.launch_blocked,
            "terminal_reason": self.terminal_reason,
            "concurrency": self.concurrency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "samples": [
                sample.public()
                for sample in sorted(
                    self.samples.values(),
                    key=lambda candidate: candidate.queue_position,
                )
            ],
            "aggregates": self.aggregates(),
        }

    def aggregates(self) -> dict[str, int | float]:
        states: dict[str, int] = {}
        for sample in self.samples.values():
            states[sample.state] = states.get(sample.state, 0) + 1
        return {
            "planned": len(self.samples),
            "queued": states.get("queued", 0),
            "running": states.get("launching", 0) + states.get("running", 0),
            "success": states.get("success", 0),
            "failed": states.get("agent_failure", 0)
            + states.get("setup_failure", 0)
            + states.get("interrupted", 0),
            "cancelled": states.get("cancelled", 0),
            "excluded": states.get("excluded", 0),
            "spent_usd": round(
                sum(sample.cost_usd or 0.0 for sample in self.samples.values()),
                8,
            ),
        }
