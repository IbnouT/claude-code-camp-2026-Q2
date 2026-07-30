"""Append-only per-player knowledge with provenance and resumable change capture."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .knowledge_models import (
    CONFIDENCES,
    LAYERS,
    SCHEMA_VERSION,
    Assertion,
    Change,
    EvidenceRef,
    KnowledgeError,
    KnowledgeInput,
    Snapshot,
)
from .knowledge_schema import SCHEMA


class KnowledgeStore:
    """The single writer for one player's durable learned state."""

    def __init__(self, path: Path, *, player_id: str, read_only: bool = False) -> None:
        if not player_id.strip():
            raise KnowledgeError("knowledge player id must not be empty")
        self.path = path
        self.player_id = player_id
        self.read_only = read_only
        self._writer_lock = None
        self._db: sqlite3.Connection | None = None
        try:
            if read_only:
                if not path.is_file():
                    raise KnowledgeError(f"knowledge store does not exist: {path}")
                self._db = sqlite3.connect(
                    f"file:{path}?mode=ro",
                    uri=True,
                    isolation_level=None,
                )
            else:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(path.parent, 0o700)
                lock_path = path.with_name(f"{path.name}.writer.lock")
                writer_lock = lock_path.open("a+")
                os.chmod(lock_path, 0o600)
                try:
                    fcntl.flock(
                        writer_lock.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                except BlockingIOError as error:
                    writer_lock.close()
                    raise KnowledgeError(
                        f"knowledge store already has a writer: {path}"
                    ) from error
                self._writer_lock = writer_lock
                self._db = sqlite3.connect(path, isolation_level=None)
                os.chmod(path, 0o600)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys=ON")
            version = int(self._db.execute("PRAGMA user_version").fetchone()[0])
            allowed_versions = (SCHEMA_VERSION,) if read_only else (0, SCHEMA_VERSION)
            if version not in allowed_versions:
                raise KnowledgeError(
                    f"knowledge schema version {version} is unsupported, "
                    f"expected {SCHEMA_VERSION}"
                )
            if not read_only:
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=NORMAL")
                self._db.executescript(SCHEMA)
                if version == 0:
                    self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            try:
                owner = self._db.execute(
                    "SELECT value FROM metadata WHERE key = 'player_id'"
                ).fetchone()
            except sqlite3.Error as error:
                raise KnowledgeError(
                    "knowledge store owner metadata is unavailable"
                ) from error
            if owner is None:
                if read_only:
                    raise KnowledgeError("knowledge store has no player owner")
                self._db.execute(
                    "INSERT INTO metadata (key, value) VALUES ('player_id', ?)",
                    (player_id,),
                )
            elif str(owner["value"]) != player_id:
                raise KnowledgeError(
                    f"knowledge store belongs to player {owner['value']!r}, "
                    f"not {player_id!r}"
                )
        except Exception:
            if self._db is not None:
                self._db.close()
            self._release_writer_lock()
            raise

    def assert_fact(
        self,
        subject: str,
        predicate: str,
        value: Any,
        *,
        layer: str,
        confidence: str,
        evidence: EvidenceRef,
        transaction_id: str | None = None,
    ) -> Assertion:
        """Append a claim, or add evidence when the current value is unchanged."""
        self._writable()
        if layer not in LAYERS:
            raise KnowledgeError(f"unknown knowledge layer {layer!r}")
        if confidence not in CONFIDENCES:
            raise KnowledgeError(f"unknown knowledge confidence {confidence!r}")
        if not subject or not predicate:
            raise KnowledgeError("knowledge subject and predicate must not be empty")
        _validate_evidence(evidence)
        value_json = _canonical(value)
        value_digest = _digest(value_json)
        tx = transaction_id or uuid.uuid4().hex
        now = time.time()
        with self._transaction():
            return self._assert_fact(
                subject,
                predicate,
                value_json,
                value_digest,
                layer=layer,
                confidence=confidence,
                evidence=evidence,
                transaction_id=tx,
                now=now,
                force_append=False,
            )

    def resolve(
        self,
        fact_id: str,
        assertion_id: str,
        *,
        reason: str,
        transaction_id: str | None = None,
    ) -> None:
        """Select one retained assertion without deleting its alternatives."""
        self._writable()
        if not reason.strip():
            raise KnowledgeError("resolution reason must not be empty")
        tx = transaction_id or uuid.uuid4().hex
        now = time.time()
        with self._transaction():
            fact = self._db.execute(
                "SELECT current_assertion_id FROM facts WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            chosen = self._db.execute(
                "SELECT value_digest, status FROM assertions "
                "WHERE assertion_id = ? AND fact_id = ?",
                (assertion_id, fact_id),
            ).fetchone()
            if fact is None or chosen is None:
                raise KnowledgeError("resolution must name an assertion of the fact")
            if chosen["status"] == "retracted":
                raise KnowledgeError("a retracted assertion cannot resolve a fact")
            before = self._assertion_row(fact["current_assertion_id"])
            self._db.execute(
                "INSERT INTO resolutions "
                "(resolution_id, fact_id, assertion_id, reason, transaction_id, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, fact_id, assertion_id, reason, tx, now),
            )
            self._db.execute(
                "UPDATE facts SET current_assertion_id = ? WHERE fact_id = ?",
                (assertion_id, fact_id),
            )
            self._change(
                tx,
                "resolve",
                "fact",
                fact_id,
                None if before is None else str(before["value_digest"]),
                str(chosen["value_digest"]),
                None,
                now,
            )

    def snapshot(self, reason: str) -> Snapshot:
        """Record the current materialized assertion set before mutation."""
        self._writable()
        if not reason.strip():
            raise KnowledgeError("snapshot reason must not be empty")
        with self._transaction():
            rows = self._db.execute(
                "SELECT current_assertion_id FROM facts "
                "WHERE current_assertion_id IS NOT NULL "
                "ORDER BY current_assertion_id"
            ).fetchall()
            assertion_ids = [str(row["current_assertion_id"]) for row in rows]
            high_water = self.last_change_seq()
            generation = int(
                self._db.execute(
                    "SELECT COALESCE(MAX(generation), 0) + 1 AS generation "
                    "FROM snapshots"
                ).fetchone()["generation"]
            )
            snapshot_id = uuid.uuid4().hex
            digest = _digest(_canonical(assertion_ids))
            now = time.time()
            self._db.execute(
                "INSERT INTO snapshots "
                "(snapshot_id, cdc_high_water, reason, digest, generation, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (snapshot_id, high_water, reason, digest, generation, now),
            )
            self._db.executemany(
                "INSERT INTO snapshot_facts (snapshot_id, assertion_id) "
                "VALUES (?, ?)",
                ((snapshot_id, assertion_id) for assertion_id in assertion_ids),
            )
            self._change(
                uuid.uuid4().hex,
                "snapshot",
                "snapshot",
                snapshot_id,
                None,
                digest,
                None,
                now,
            )
        return Snapshot(snapshot_id, high_water, reason, digest, generation, now)

    def reset_learned(self, *, reason: str, snapshot_id: str) -> int:
        """Append retractions for current learned facts after a verified reset."""
        self._writable()
        if not reason.strip():
            raise KnowledgeError("knowledge reset reason must not be empty")
        if not self.verify_snapshot(snapshot_id):
            raise KnowledgeError(
                f"knowledge snapshot {snapshot_id!r} is missing or invalid"
            )
        tx = uuid.uuid4().hex
        now = time.time()
        rows = self._db.execute(
            "SELECT f.fact_id, f.current_assertion_id, a.* "
            "FROM facts AS f JOIN assertions AS a "
            "ON a.assertion_id = f.current_assertion_id "
            "WHERE f.layer = 'learned'"
        ).fetchall()
        with self._transaction():
            for row in rows:
                assertion_id = uuid.uuid4().hex
                self._db.execute(
                    "INSERT INTO assertions "
                    "(assertion_id, fact_id, value_json, value_digest, status, "
                    "confidence, method, parser_version, session_id, source_seq, "
                    "wire_digest, observed_at, supersedes, conflict_group, transaction_id) "
                    "VALUES (?, ?, ?, ?, 'retracted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        assertion_id,
                        row["fact_id"],
                        row["value_json"],
                        row["value_digest"],
                        row["confidence"],
                        f"knowledge-reset:{reason}",
                        row["parser_version"],
                        row["session_id"],
                        row["source_seq"],
                        row["wire_digest"],
                        now,
                        row["assertion_id"],
                        row["conflict_group"],
                        tx,
                    ),
                )
                self._db.execute(
                    "UPDATE facts SET current_assertion_id = NULL WHERE fact_id = ?",
                    (row["fact_id"],),
                )
                self._change(
                    tx,
                    "retract",
                    "assertion",
                    assertion_id,
                    str(row["value_digest"]),
                    None,
                    None,
                    now,
                )
        return len(rows)

    def restore(self, snapshot_id: str, *, reason: str) -> int:
        """Append current assertions derived from a retained snapshot."""
        self._writable()
        if not reason.strip():
            raise KnowledgeError("knowledge restore reason must not be empty")
        if not self.verify_snapshot(snapshot_id):
            raise KnowledgeError(
                f"knowledge snapshot {snapshot_id!r} is missing or invalid"
            )
        rows = self._db.execute(
            "SELECT f.subject, f.predicate, f.layer, a.* "
            "FROM snapshot_facts AS sf "
            "JOIN assertions AS a ON a.assertion_id = sf.assertion_id "
            "JOIN facts AS f ON f.fact_id = a.fact_id "
            "WHERE sf.snapshot_id = ? ORDER BY sf.assertion_id",
            (snapshot_id,),
        ).fetchall()
        restore_id = uuid.uuid4().hex
        tx = uuid.uuid4().hex
        with self._transaction():
            for row in rows:
                now = time.time()
                evidence = EvidenceRef(
                    session_id=str(row["session_id"]),
                    source_seq=int(row["source_seq"]),
                    wire_digest=str(row["wire_digest"]),
                    parser_version=str(row["parser_version"]),
                    method=f"snapshot-restore:{reason}",
                    observed_at=now,
                )
                self._assert_fact(
                    str(row["subject"]),
                    str(row["predicate"]),
                    str(row["value_json"]),
                    str(row["value_digest"]),
                    layer=str(row["layer"]),
                    confidence=str(row["confidence"]),
                    evidence=evidence,
                    transaction_id=tx,
                    now=now,
                    force_append=True,
                    supersedes=str(row["assertion_id"]),
                )
            self._db.execute(
                "INSERT INTO restores "
                "(restore_id, snapshot_id, reason, assertions, transaction_id, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (restore_id, snapshot_id, reason, len(rows), tx, time.time()),
            )
        return len(rows)

    def rebuild(
        self,
        inputs: Iterable[KnowledgeInput],
        *,
        parser_version: str,
        session_order: Mapping[str, int],
    ) -> str:
        """Append migrated assertions in registry-session then source order."""
        self._writable()
        if not parser_version.strip():
            raise KnowledgeError("parser rebuild version must not be empty")
        rebuild_id = uuid.uuid4().hex
        tx = uuid.uuid4().hex
        first_at: float | None = None
        last_at: float | None = None
        count = 0
        ordered = list(inputs)
        missing = {
            item.evidence.session_id
            for item in ordered
            if item.evidence.session_id not in session_order
        }
        if missing:
            raise KnowledgeError(
                f"parser rebuild lacks registry order for sessions {sorted(missing)}"
            )
        if len(set(session_order.values())) != len(session_order):
            raise KnowledgeError("parser rebuild registry order must be unique")
        for item in ordered:
            if item.layer not in LAYERS:
                raise KnowledgeError(f"unknown knowledge layer {item.layer!r}")
            if item.confidence not in CONFIDENCES:
                raise KnowledgeError(
                    f"unknown knowledge confidence {item.confidence!r}"
                )
            if not item.subject or not item.predicate:
                raise KnowledgeError(
                    "knowledge subject and predicate must not be empty"
                )
            _validate_evidence(item.evidence)
        ordered.sort(
            key=lambda item: (
                session_order[item.evidence.session_id],
                item.evidence.source_seq,
            )
        )
        now = time.time()
        with self._transaction():
            for item in ordered:
                first_at = (
                    item.evidence.observed_at if first_at is None else first_at
                )
                last_at = item.evidence.observed_at
                evidence = EvidenceRef(
                    session_id=item.evidence.session_id,
                    source_seq=item.evidence.source_seq,
                    wire_digest=item.evidence.wire_digest,
                    parser_version=parser_version,
                    method=f"parser-rebuild:{item.evidence.method}",
                    observed_at=item.evidence.observed_at,
                )
                value_json = _canonical(item.value)
                self._assert_fact(
                    item.subject,
                    item.predicate,
                    value_json,
                    _digest(value_json),
                    layer=item.layer,
                    confidence=item.confidence,
                    evidence=evidence,
                    transaction_id=tx,
                    now=item.evidence.observed_at,
                    force_append=True,
                )
                count += 1
            self._db.execute(
                "INSERT INTO rebuilds "
                "(rebuild_id, parser_version, source_first_at, source_last_at, "
                "assertions, transaction_id, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rebuild_id, parser_version, first_at, last_at, count, tx, now),
            )
            self._change(
                tx,
                "rebuild",
                "rebuild",
                rebuild_id,
                None,
                _digest(_canonical({"parser_version": parser_version, "count": count})),
                None,
                now,
            )
        return rebuild_id

    def current_facts(self, *, layer: str | None = None) -> list[Assertion]:
        sql = (
            "SELECT a.assertion_id FROM facts AS f JOIN assertions AS a "
            "ON a.assertion_id = f.current_assertion_id"
        )
        args: tuple[Any, ...] = ()
        if layer is not None:
            sql += " WHERE f.layer = ?"
            args = (layer,)
        sql += " ORDER BY f.subject, f.predicate, f.layer"
        return [
            self._assertion(str(row["assertion_id"]))
            for row in self._db.execute(sql, args)
        ]

    def changes_since(self, after: int = 0) -> list[Change]:
        return [
            Change(
                change_seq=int(row["change_seq"]),
                transaction_id=str(row["transaction_id"]),
                operation=str(row["operation"]),
                entity_type=str(row["entity_type"]),
                entity_id=str(row["entity_id"]),
                before_digest=row["before_digest"],
                after_digest=row["after_digest"],
                session_id=row["session_id"],
                source_seq=row["source_seq"],
                at=float(row["at"]),
            )
            for row in self._db.execute(
                "SELECT * FROM changes WHERE change_seq > ? ORDER BY change_seq",
                (after,),
            )
        ]

    def last_change_seq(self) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(change_seq), 0) AS seq FROM changes"
        ).fetchone()
        return int(row["seq"])

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        row = self._db.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return Snapshot(
            snapshot_id=str(row["snapshot_id"]),
            cdc_high_water=int(row["cdc_high_water"]),
            reason=str(row["reason"]),
            digest=str(row["digest"]),
            generation=int(row["generation"]),
            at=float(row["at"]),
        )

    def verify_snapshot(self, snapshot_id: str) -> bool:
        """Recompute one snapshot digest and reject missing assertion rows."""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            return False
        rows = self._db.execute(
            "SELECT sf.assertion_id, a.assertion_id AS present "
            "FROM snapshot_facts AS sf "
            "LEFT JOIN assertions AS a ON a.assertion_id = sf.assertion_id "
            "WHERE sf.snapshot_id = ? ORDER BY sf.assertion_id",
            (snapshot_id,),
        ).fetchall()
        if any(row["present"] is None for row in rows):
            return False
        assertion_ids = [str(row["assertion_id"]) for row in rows]
        return _digest(_canonical(assertion_ids)) == snapshot.digest

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._release_writer_lock()

    def _release_writer_lock(self) -> None:
        if self._writer_lock is not None:
            fcntl.flock(self._writer_lock.fileno(), fcntl.LOCK_UN)
            self._writer_lock.close()
            self._writer_lock = None

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        else:
            self._db.execute("COMMIT")

    def _assert_fact(
        self,
        subject: str,
        predicate: str,
        value_json: str,
        value_digest: str,
        *,
        layer: str,
        confidence: str,
        evidence: EvidenceRef,
        transaction_id: str,
        now: float,
        force_append: bool,
        supersedes: str | None = None,
    ) -> Assertion:
        fact = self._db.execute(
            "SELECT * FROM facts WHERE subject = ? AND predicate = ? AND layer = ?",
            (subject, predicate, layer),
        ).fetchone()
        if fact is None:
            fact_id = _stable_id("fact", subject, predicate, layer)
            self._db.execute(
                "INSERT INTO facts "
                "(fact_id, subject, predicate, layer, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (fact_id, subject, predicate, layer, now),
            )
            current = None
        else:
            fact_id = str(fact["fact_id"])
            current = self._assertion_row(fact["current_assertion_id"])

        matching = self._db.execute(
            "SELECT * FROM assertions "
            "WHERE fact_id = ? AND value_digest = ? AND status != 'retracted' "
            "ORDER BY CASE WHEN transaction_id = ? THEN 0 ELSE 1 END, "
            "observed_at DESC, assertion_id DESC LIMIT 1",
            (fact_id, value_digest, transaction_id),
        ).fetchone()
        if matching is not None and (
            not force_append or matching["transaction_id"] == transaction_id
        ):
            self._add_evidence(str(matching["assertion_id"]), evidence)
            self._change(
                transaction_id,
                "support",
                "assertion",
                str(matching["assertion_id"]),
                value_digest,
                value_digest,
                evidence,
                now,
            )
            return self._assertion(str(matching["assertion_id"]))

        assertion_id = uuid.uuid4().hex
        conflict_group = None
        status = "active"
        equivalent_current = (
            current is not None and current["value_digest"] == value_digest
        )
        if current is not None and not equivalent_current:
            status = "conflicted"
            conflict_group = (
                str(current["conflict_group"])
                if current["conflict_group"]
                else _stable_id("conflict", fact_id)
            )
        self._db.execute(
            "INSERT INTO assertions "
            "(assertion_id, fact_id, value_json, value_digest, status, "
            "confidence, method, parser_version, session_id, source_seq, "
            "wire_digest, observed_at, supersedes, conflict_group, transaction_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                assertion_id,
                fact_id,
                value_json,
                value_digest,
                status,
                confidence,
                evidence.method,
                evidence.parser_version,
                evidence.session_id,
                evidence.source_seq,
                evidence.wire_digest,
                evidence.observed_at,
                supersedes
                if supersedes is not None
                else None if current is None else str(current["assertion_id"]),
                conflict_group,
                transaction_id,
            ),
        )
        self._add_evidence(assertion_id, evidence)
        if current is None or equivalent_current:
            self._db.execute(
                "UPDATE facts SET current_assertion_id = ? WHERE fact_id = ?",
                (assertion_id, fact_id),
            )
        self._change(
            transaction_id,
            (
                "assert"
                if current is None
                else "supersede" if equivalent_current else "conflict"
            ),
            "assertion",
            assertion_id,
            None if current is None else str(current["value_digest"]),
            value_digest,
            evidence,
            now,
        )
        return self._assertion(assertion_id)

    def _assertion(self, assertion_id: str) -> Assertion:
        row = self._db.execute(
            "SELECT a.*, f.subject, f.predicate, f.layer "
            "FROM assertions AS a JOIN facts AS f ON f.fact_id = a.fact_id "
            "WHERE a.assertion_id = ?",
            (assertion_id,),
        ).fetchone()
        if row is None:
            raise KnowledgeError(f"unknown assertion {assertion_id!r}")
        evidence_rows = self._db.execute(
            "SELECT * FROM evidence_refs WHERE assertion_id = ? "
            "ORDER BY observed_at, evidence_id",
            (assertion_id,),
        ).fetchall()
        first_evidence = _evidence(evidence_rows[0])
        latest_evidence = _evidence(evidence_rows[-1])
        return Assertion(
            assertion_id=str(row["assertion_id"]),
            fact_id=str(row["fact_id"]),
            subject=str(row["subject"]),
            predicate=str(row["predicate"]),
            value=json.loads(row["value_json"]),
            layer=str(row["layer"]),
            status=str(row["status"]),
            confidence=str(row["confidence"]),
            evidence=first_evidence,
            latest_evidence=latest_evidence,
            conflict_group=row["conflict_group"],
        )

    def _assertion_row(self, assertion_id: Any) -> sqlite3.Row | None:
        if assertion_id is None:
            return None
        return self._db.execute(
            "SELECT * FROM assertions WHERE assertion_id = ?",
            (assertion_id,),
        ).fetchone()

    def _add_evidence(self, assertion_id: str, evidence: EvidenceRef) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO evidence_refs "
            "(assertion_id, session_id, source_seq, wire_digest, parser_version, "
            "method, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                assertion_id,
                evidence.session_id,
                evidence.source_seq,
                evidence.wire_digest,
                evidence.parser_version,
                evidence.method,
                evidence.observed_at,
            ),
        )

    def _change(
        self,
        transaction_id: str,
        operation: str,
        entity_type: str,
        entity_id: str,
        before_digest: str | None,
        after_digest: str | None,
        evidence: EvidenceRef | None,
        at: float,
    ) -> None:
        self._db.execute(
            "INSERT INTO changes "
            "(transaction_id, operation, entity_type, entity_id, before_digest, "
            "after_digest, session_id, source_seq, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                transaction_id,
                operation,
                entity_type,
                entity_id,
                before_digest,
                after_digest,
                None if evidence is None else evidence.session_id,
                None if evidence is None else evidence.source_seq,
                at,
            ),
        )

    def _writable(self) -> None:
        if self.read_only:
            raise KnowledgeError("knowledge store is read-only")

    def __str__(self) -> str:
        return (
            f"<KnowledgeStore player={self.player_id} "
            f"changes={self.last_change_seq()} path={self.path.name}>"
        )


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as error:
        raise KnowledgeError(f"knowledge value is not JSON serializable: {error}") from error


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def _evidence(row: sqlite3.Row) -> EvidenceRef:
    return EvidenceRef(
        session_id=str(row["session_id"]),
        source_seq=int(row["source_seq"]),
        wire_digest=str(row["wire_digest"]),
        parser_version=str(row["parser_version"]),
        method=str(row["method"]),
        observed_at=float(row["observed_at"]),
    )


def _validate_evidence(evidence: EvidenceRef) -> None:
    if not evidence.session_id:
        raise KnowledgeError("knowledge evidence session must not be empty")
    if evidence.source_seq < 0:
        raise KnowledgeError("knowledge evidence sequence must not be negative")
    if not evidence.wire_digest:
        raise KnowledgeError("knowledge evidence wire digest must not be empty")
    if not evidence.parser_version:
        raise KnowledgeError("knowledge evidence parser version must not be empty")
    if not evidence.method:
        raise KnowledgeError("knowledge evidence method must not be empty")
