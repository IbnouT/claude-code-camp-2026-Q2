"""Typed public contracts for observatory sources and investigations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceStatus(BaseModel):
    """One evidence source and its current availability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["gateway", "agent", "benchmark", "knowledge"]
    label: str
    state: Literal["ready", "unavailable", "disabled"]
    detail: str
    contract_digest: str | None = None


class ObservatoryCapabilities(BaseModel):
    """The exact sources and features available to this installation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    sources: tuple[SourceStatus, ...]
    features: tuple[str, ...]


class RunSummary(BaseModel):
    """One recorded benchmark attempt available for investigation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    journey: str
    attempt: str
    success: bool
    stop_reason: str
    iterations: int
    cost_usd: float
    result_mode: str


class EvidenceCitation(BaseModel):
    """One exact piece of evidence behind a diagnostic or lens value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: Literal["agent", "gateway", "benchmark"]
    label: str
    sequence: int | None = None
    trace_id: str | None = None
    excerpt: str


class InvestigationEvent(BaseModel):
    """One sanitized causal event from a recorded run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int
    at: str
    phase: str
    label: str
    cost_usd: float = 0
    duration_ms: float = 0
    parent: int | None = None
    citation: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class DiagnosticRecord(BaseModel):
    """A deterministic finding with its trigger and evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal[
        "false_completion",
        "position_ambiguity",
        "confusion_loop",
        "stall",
        "parse_degradation",
    ]
    severity: Literal["critical", "warning", "notice"]
    title: str
    detail: str
    mechanism: str
    at: int
    evidence: tuple[str, ...]


class EvidenceForm(BaseModel):
    """One layer in the wire-to-truth evidence lens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["available", "missing"]
    title: str
    text: str
    citations: tuple[str, ...] = ()


class EvidenceLens(BaseModel):
    """Five non-interchangeable forms of one selected run outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wire: EvidenceForm
    parsed: EvidenceForm
    rendered: EvidenceForm
    believed: EvidenceForm
    truth: EvidenceForm


class WorldNode(BaseModel):
    """One distinct inferred place, never just a room title."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    place: int
    title: str
    exits: tuple[str, ...]
    visits: int
    first_seq: int
    last_seq: int
    state: Literal["observed", "candidate", "current"]
    confidence: str
    method: str


class WorldEdge(BaseModel):
    """One observed transition between distinct inferred places."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    target: str
    direction: str
    traversals: int
    evidence: tuple[int, ...]


class WorldProjection(BaseModel):
    """The evidence-backed journey graph and its unresolved current state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[WorldNode, ...]
    edges: tuple[WorldEdge, ...]
    current_title: str | None
    current_confidence: str
    candidates: tuple[str, ...]
    parse_miss_rate: float
    unknown_positions: int


class Investigation(BaseModel):
    """A reproducible diagnosis of one benchmark attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run: RunSummary
    events: tuple[InvestigationEvent, ...]
    diagnostics: tuple[DiagnosticRecord, ...]
    citations: tuple[EvidenceCitation, ...]
    lens: EvidenceLens
    world: WorldProjection
