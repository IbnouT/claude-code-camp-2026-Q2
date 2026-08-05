"""Typed public contracts for one player's authoritative knowledge state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeEvidence(BaseModel):
    """One exact gateway observation supporting an assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    source_seq: int
    wire_digest: str
    parser_version: str
    method: str
    observed_at: float


class KnowledgeAssertionRecord(BaseModel):
    """One immutable assertion with all retained support."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assertion_id: str
    fact_id: str
    subject: str
    predicate: str
    value: Any
    layer: Literal["belief", "parsed", "learned", "observer_truth"]
    status: str
    confidence: str
    current: bool
    conflict_group: str | None
    evidence: tuple[KnowledgeEvidence, ...]


class KnowledgeChangeRecord(BaseModel):
    """One append-only change after a per-player global cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_seq: int
    transaction_id: str
    operation: str
    entity_type: str
    entity_id: str
    before_digest: str | None
    after_digest: str | None
    session_id: str | None
    source_seq: int | None
    at: float


class KnowledgeSnapshotRecord(BaseModel):
    """One retained snapshot with current integrity verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    cdc_high_water: int
    reason: str
    digest: str
    generation: int
    at: float
    verified: bool


class KnowledgeRecoveryRecord(BaseModel):
    """One append-only reset or restore operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["reset", "restore"]
    operation_id: str
    snapshot_id: str
    reason: str
    assertions: int
    transaction_id: str
    at: float


class KnowledgeMetricRecord(BaseModel):
    """One evidence-derived count for progressive overview."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    value: int | float
    detail: str


class PlayerKnowledge(BaseModel):
    """Complete read-only knowledge state for exactly one player."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    player_id: str
    state: Literal["ready", "unavailable", "incomplete"]
    source: Literal["per-player durable knowledge"]
    cdc_cursor: int
    metrics: tuple[KnowledgeMetricRecord, ...]
    assertions: tuple[KnowledgeAssertionRecord, ...]
    changes: tuple[KnowledgeChangeRecord, ...]
    snapshots: tuple[KnowledgeSnapshotRecord, ...]
    recoveries: tuple[KnowledgeRecoveryRecord, ...]
    capture_gaps: tuple[str, ...] = ()


class KnowledgeRecoveryRequest(BaseModel):
    """One confirmed action bound to the current live session sequence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    action: Literal["reset", "restore"]
    session_id: str = Field(min_length=1, max_length=200)
    expected_sequence: int = Field(ge=0)
    confirmed: Literal[True]
    reason: str = Field(min_length=1, max_length=240)
    snapshot_id: str | None = Field(default=None, max_length=200)
