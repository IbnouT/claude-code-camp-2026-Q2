"""Typed outcomes and measurements for one materializer advancement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AdvanceKind = Literal[
    "bootstrap",
    "incremental",
    "recovered",
    "unchanged",
    "fault",
]


@dataclass(frozen=True, slots=True)
class AdvanceMetrics:
    """Exact retained suffix coordinates read by one advancement."""

    agent_start_offset: int
    agent_records: int
    gateway_after_sequence: int
    gateway_records: int
    lifecycle_after_sequence: int
    lifecycle_records: int
    passes: int = 1


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    """One complete materializer outcome visible to later resource layers."""

    session_id: str
    cursor: str
    generation: int
    kind: AdvanceKind
    terminal: bool
    more_available: bool
    fault: str | None
    metrics: AdvanceMetrics
