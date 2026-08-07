"""Public data contracts for per-player knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
# "derived" holds what was computed from other facts, so it is dropped and
# recomputed rather than corrected. Nothing observed is ever written there.
LAYERS = frozenset(
    {"belief", "parsed", "learned", "observer_truth", "derived"}
)
CONFIDENCES = frozenset(
    {"high", "medium", "low", "confirmed", "tracked", "ambiguous", "unknown"}
)


class KnowledgeError(RuntimeError):
    """The per-player knowledge store rejected an operation."""


@dataclass(frozen=True)
class EvidenceRef:
    """Exact gateway evidence behind one assertion."""

    session_id: str
    source_seq: int
    wire_digest: str
    parser_version: str
    method: str
    observed_at: float


@dataclass(frozen=True)
class Assertion:
    """One immutable claim about a stable fact."""

    assertion_id: str
    fact_id: str
    subject: str
    predicate: str
    value: Any
    layer: str
    status: str
    confidence: str
    evidence: EvidenceRef
    latest_evidence: EvidenceRef
    conflict_group: str | None = None


@dataclass(frozen=True)
class Change:
    """One committed CDC record with a per-player global cursor."""

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


@dataclass(frozen=True)
class Snapshot:
    """A recoverable set of current assertion identifiers."""

    snapshot_id: str
    cdc_high_water: int
    reason: str
    digest: str
    generation: int
    at: float


@dataclass(frozen=True)
class Recovery:
    """One append-only reset or restore linked to its verified snapshot."""

    operation: str
    operation_id: str
    snapshot_id: str
    reason: str
    assertions: int
    transaction_id: str
    at: float


@dataclass(frozen=True)
class KnowledgeInput:
    """A parsed fact ready for deterministic rebuild."""

    subject: str
    predicate: str
    value: Any
    layer: str
    confidence: str
    evidence: EvidenceRef
