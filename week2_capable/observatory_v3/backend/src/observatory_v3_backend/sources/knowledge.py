"""Read-only source for one player's authoritative gateway knowledge."""

from __future__ import annotations

import re
from pathlib import Path

from mud_gateway.knowledge import KnowledgeError, KnowledgeStore

from ..knowledge_contracts import (
    KnowledgeAssertionRecord,
    KnowledgeChangeRecord,
    KnowledgeEvidence,
    KnowledgeMetricRecord,
    KnowledgeRecoveryRecord,
    KnowledgeSnapshotRecord,
    PlayerKnowledge,
)

PLAYER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


class KnowledgeSourceError(RuntimeError):
    """The requested per-player knowledge source cannot be read safely."""


class KnowledgeSource:
    """Discover and project owned knowledge without acquiring a writer lock."""

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root.resolve()

    def read(self, player_id: str, *, after: int = 0) -> PlayerKnowledge:
        """Read one player's complete state and changes after a CDC cursor."""

        if not PLAYER_ID.fullmatch(player_id):
            raise KnowledgeSourceError("invalid player id")
        path = (self.runtime_root / "profiles" / player_id / "knowledge.db").resolve()
        expected_parent = (self.runtime_root / "profiles" / player_id).resolve()
        if path.parent != expected_parent:
            raise KnowledgeSourceError("knowledge path escaped the player profile")
        if not path.is_file():
            return _unavailable(player_id)
        try:
            store = KnowledgeStore(path, player_id=player_id, read_only=True)
        except KnowledgeError as error:
            raise KnowledgeSourceError(str(error)) from error
        try:
            current = {assertion.assertion_id for assertion in store.current_facts()}
            assertions = tuple(
                KnowledgeAssertionRecord(
                    assertion_id=assertion.assertion_id,
                    fact_id=assertion.fact_id,
                    subject=assertion.subject,
                    predicate=assertion.predicate,
                    value=assertion.value,
                    layer=assertion.layer,
                    status=assertion.status,
                    confidence=assertion.confidence,
                    current=assertion.assertion_id in current,
                    conflict_group=assertion.conflict_group,
                    evidence=tuple(
                        KnowledgeEvidence(
                            session_id=evidence.session_id,
                            source_seq=evidence.source_seq,
                            wire_digest=evidence.wire_digest,
                            parser_version=evidence.parser_version,
                            method=evidence.method,
                            observed_at=evidence.observed_at,
                        )
                        for evidence in store.evidence_for(assertion.assertion_id)
                    ),
                )
                for assertion in store.assertions()
            )
            changes = tuple(
                KnowledgeChangeRecord(**change.__dict__)
                for change in store.changes_since(after)
            )
            snapshots = tuple(
                KnowledgeSnapshotRecord(
                    **snapshot.__dict__,
                    verified=store.verify_snapshot(snapshot.snapshot_id),
                )
                for snapshot in store.snapshots()
            )
            recoveries = tuple(
                KnowledgeRecoveryRecord(**recovery.__dict__)
                for recovery in store.recoveries()
            )
            gaps = tuple(
                f"snapshot {snapshot.snapshot_id} failed integrity verification"
                for snapshot in snapshots
                if not snapshot.verified
            )
            return PlayerKnowledge(
                player_id=player_id,
                state="incomplete" if gaps else "ready",
                source="per-player durable knowledge",
                cdc_cursor=store.last_change_seq(),
                metrics=_metrics(assertions),
                assertions=assertions,
                changes=changes,
                snapshots=snapshots,
                recoveries=recoveries,
                capture_gaps=gaps,
            )
        finally:
            store.close()


def _metrics(
    assertions: tuple[KnowledgeAssertionRecord, ...],
) -> tuple[KnowledgeMetricRecord, ...]:
    current = tuple(item for item in assertions if item.current)
    subjects = {item.subject for item in current}
    conflicts = {
        item.conflict_group for item in assertions if item.conflict_group is not None
    }
    sessions = {
        evidence.session_id for item in assertions for evidence in item.evidence
    }
    return (
        KnowledgeMetricRecord(
            id="current-facts",
            label="Current facts",
            value=len(current),
            detail="Materialized assertions selected by the knowledge store.",
        ),
        KnowledgeMetricRecord(
            id="subjects",
            label="Known subjects",
            value=len(subjects),
            detail="Distinct player, place, entity, and progression subjects.",
        ),
        KnowledgeMetricRecord(
            id="conflicts",
            label="Open conflicts",
            value=len(conflicts),
            detail="Contradiction groups retained until explicit resolution.",
        ),
        KnowledgeMetricRecord(
            id="source-sessions",
            label="Source sessions",
            value=len(sessions),
            detail="Sessions contributing at least one retained observation.",
        ),
    )


def _unavailable(player_id: str) -> PlayerKnowledge:
    return PlayerKnowledge(
        player_id=player_id,
        state="unavailable",
        source="per-player durable knowledge",
        cdc_cursor=0,
        metrics=(),
        assertions=(),
        changes=(),
        snapshots=(),
        recoveries=(),
        capture_gaps=("knowledge store is not available for this player",),
    )
