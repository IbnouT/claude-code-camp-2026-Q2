"""Bounded direct reads from one player-owned durable knowledge store."""

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from ..database import open_readonly_database
from ..redaction import sanitize_evidence
from .bounds import bounded_json_object, content_identity
from .content import value_chunk
from .contracts import (
    KnowledgeDetailPage,
    KnowledgeEvidencePage,
    KnowledgeEvidenceRef,
    KnowledgeItem,
    KnowledgeMetric,
    KnowledgeSummaryResponse,
    ValueChunkResponse,
)
from .cursor import CursorCoordinates, decode_cursor, encode_cursor
from .repository import ResourceNotFoundError, ResourceUnavailableError

KnowledgeKind = Literal["assertion", "change", "snapshot", "recovery"]


class KnowledgeResourceRepository:
    """Read fixed summaries and keyset pages without hydrating all knowledge."""

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root.resolve()

    def summary(self, player_id: str) -> KnowledgeSummaryResponse:
        """Return fixed totals and freshness for one validated player."""
        source = self._source(player_id)
        if source is None:
            return KnowledgeSummaryResponse(
                **_metadata(
                    player_id,
                    "summary",
                    version=1,
                    cursor=0,
                    gaps=("knowledge_store_unavailable",),
                ),
                player_id=player_id,
                cdc_cursor=0,
                metrics=(),
            )
        try:
            with open_readonly_database(source) as database:
                row = database.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM facts
                         WHERE current_assertion_id IS NOT NULL) AS current_facts,
                        (SELECT COUNT(DISTINCT subject) FROM facts
                         WHERE current_assertion_id IS NOT NULL) AS subjects,
                        (SELECT COUNT(DISTINCT conflict_group) FROM assertions
                         WHERE conflict_group IS NOT NULL) AS conflicts,
                        (SELECT COUNT(DISTINCT session_id) FROM evidence_refs)
                            AS source_sessions,
                        (SELECT COALESCE(MAX(change_seq), 0) FROM changes)
                            AS cdc_cursor
                    """
                ).fetchone()
        except sqlite3.Error as error:
            raise ResourceUnavailableError(
                "knowledge summary cannot be read"
            ) from error
        if row is None:
            raise ResourceUnavailableError("knowledge summary is absent")
        cursor = int(row["cdc_cursor"])
        return KnowledgeSummaryResponse(
            **_metadata(
                player_id,
                "summary",
                version=max(1, cursor),
                cursor=cursor,
            ),
            player_id=player_id,
            cdc_cursor=cursor,
            metrics=(
                KnowledgeMetric(id="current-facts", value=int(row["current_facts"])),
                KnowledgeMetric(id="subjects", value=int(row["subjects"])),
                KnowledgeMetric(id="conflicts", value=int(row["conflicts"])),
                KnowledgeMetric(
                    id="source-sessions",
                    value=int(row["source_sessions"]),
                ),
            ),
        )

    def detail(
        self,
        player_id: str,
        kind: KnowledgeKind,
        *,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeDetailPage:
        """Return one bounded knowledge layer page with exact provenance."""
        if not 1 <= limit <= 100:
            raise ValueError("knowledge limit must be between 1 and 100")
        source = self._source(player_id)
        if source is None:
            raise ResourceUnavailableError("knowledge store is unavailable")
        resource_id = f"knowledge:{player_id}:{kind}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        try:
            with open_readonly_database(source) as database:
                cdc = _cdc_cursor(database)
                rows = _knowledge_rows(
                    database,
                    kind,
                    after=after,
                    limit=limit + 1,
                )
                items, evidence_truncated = _knowledge_items(
                    database,
                    player_id,
                    kind,
                    rows[:limit],
                )
        except sqlite3.Error as error:
            raise ResourceUnavailableError("knowledge page cannot be read") from error
        continuation = (
            _knowledge_cursor(resource_id, kind, rows[limit - 1])
            if len(rows) > limit and items
            else None
        )
        gaps = ("knowledge_evidence_truncated",) if evidence_truncated else ()
        return KnowledgeDetailPage(
            **_metadata(
                player_id,
                kind,
                version=max(1, cdc),
                cursor=cdc,
                gaps=gaps,
            ),
            player_id=player_id,
            kind=kind,
            continuation_cursor=continuation,
            items=items,
        )

    def evidence_page(
        self,
        player_id: str,
        assertion_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeEvidencePage:
        """Return every retained assertion evidence ref through bounded keysets."""
        if not 1 <= limit <= 100:
            raise ValueError("knowledge evidence limit must be between 1 and 100")
        source = self._source(player_id)
        if source is None:
            raise ResourceUnavailableError("knowledge store is unavailable")
        resource_id = f"knowledge:{player_id}:assertion:{assertion_id}:evidence"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        after_id = 0 if after is None else _positive_int(after.primary)
        try:
            with open_readonly_database(source) as database:
                assertion = database.execute(
                    "SELECT 1 FROM assertions WHERE assertion_id = ?",
                    (assertion_id,),
                ).fetchone()
                if assertion is None:
                    raise ResourceNotFoundError(assertion_id)
                cdc = _cdc_cursor(database)
                rows = database.execute(
                    """
                    SELECT *
                    FROM evidence_refs
                    WHERE assertion_id = ? AND evidence_id > ?
                    ORDER BY evidence_id
                    LIMIT ?
                    """,
                    (assertion_id, after_id, limit + 1),
                ).fetchall()
        except sqlite3.Error as error:
            raise ResourceUnavailableError(
                "knowledge evidence page cannot be read"
            ) from error
        visible = rows[:limit]
        items_list: list[KnowledgeEvidenceRef] = []
        values_truncated = False
        for row in visible:
            values, truncated = bounded_json_object(
                _sanitized_object(dict(row)),
                max_bytes=2_048,
            )
            values_truncated = values_truncated or truncated
            items_list.append(
                KnowledgeEvidenceRef(
                    id=int(row["evidence_id"]),
                    values=values,
                )
            )
        items = tuple(items_list)
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(int(visible[-1]["evidence_id"])),
                    secondary="",
                )
            )
            if len(rows) > limit and visible
            else None
        )
        version, source_cursor = content_identity(
            "obk1",
            {
                "player_id": player_id,
                "assertion_id": assertion_id,
                "cdc": cdc,
                "last_evidence_id": (0 if not rows else int(rows[-1]["evidence_id"])),
            },
        )
        return KnowledgeEvidencePage(
            resource_id=resource_id,
            resource_version=version,
            source_cursor=source_cursor,
            completeness="partial" if values_truncated else "complete",
            capture_gaps=(
                ("knowledge_evidence_values_truncated",) if values_truncated else ()
            ),
            source_refs=(f"profiles/{player_id}/knowledge.db evidence_refs",),
            player_id=player_id,
            assertion_id=assertion_id,
            continuation_cursor=continuation,
            items=items,
        )

    def assertion_content(
        self,
        player_id: str,
        assertion_id: str,
        *,
        offset: int,
        max_bytes: int,
    ) -> ValueChunkResponse:
        """Expose a full sanitized assertion value through bounded chunks."""
        source = self._source(player_id)
        if source is None:
            raise ResourceUnavailableError("knowledge store is unavailable")
        try:
            with open_readonly_database(source) as database:
                row = database.execute(
                    """
                    SELECT value_json
                    FROM assertions
                    WHERE assertion_id = ?
                    """,
                    (assertion_id,),
                ).fetchone()
                cdc = _cdc_cursor(database)
        except sqlite3.Error as error:
            raise ResourceUnavailableError(
                "knowledge assertion content cannot be read"
            ) from error
        if row is None:
            raise ResourceNotFoundError(assertion_id)
        return value_chunk(
            sanitize_evidence(json.loads(str(row["value_json"]))),
            metadata=_metadata(
                player_id,
                f"assertion:{assertion_id}:content",
                version=max(1, cdc),
                cursor=cdc,
            ),
            offset=offset,
            max_bytes=max_bytes,
        )

    def _source(self, player_id: str) -> Path | None:
        if (
            not player_id
            or len(player_id) > 120
            or any(char not in _PLAYER_CHARS for char in player_id)
        ):
            raise ValueError("player id is invalid")
        profile = (self.runtime_root / "profiles" / player_id).resolve()
        source = (profile / "knowledge.db").resolve()
        if source.parent != profile:
            raise ValueError("knowledge source escaped player profile")
        return source if source.is_file() else None


def _metadata(
    player_id: str,
    suffix: str,
    *,
    version: int,
    cursor: int,
    gaps: tuple[str, ...] = (),
) -> dict[str, Any]:
    resource_id = f"knowledge:{player_id}:{suffix}"
    return {
        "resource_id": resource_id,
        "resource_version": version,
        "source_cursor": (
            f"obk1_{sha256(f'{player_id}:{cursor}'.encode()).hexdigest()}"
        ),
        "completeness": "partial" if gaps else "complete",
        "capture_gaps": gaps,
        "source_refs": (f"profiles/{player_id}/knowledge.db",),
    }


def _cdc_cursor(database: sqlite3.Connection) -> int:
    row = database.execute(
        "SELECT COALESCE(MAX(change_seq), 0) AS value FROM changes"
    ).fetchone()
    return 0 if row is None else int(row["value"])


def _knowledge_rows(
    database: sqlite3.Connection,
    kind: KnowledgeKind,
    *,
    after: CursorCoordinates | None,
    limit: int,
) -> list[sqlite3.Row]:
    if kind == "assertion":
        where = ""
        arguments: list[object] = []
        if after is not None:
            where = "WHERE a.assertion_id > ?"
            arguments.append(after.primary)
        arguments.append(limit)
        return database.execute(
            f"""
            SELECT a.*, f.subject, f.predicate, f.layer,
                   (f.current_assertion_id = a.assertion_id) AS current
            FROM assertions AS a
            JOIN facts AS f USING (fact_id)
            {where}
            ORDER BY a.assertion_id
            LIMIT ?
            """,
            arguments,
        ).fetchall()
    if kind == "change":
        after_value = 0 if after is None else _positive_int(after.primary)
        return database.execute(
            """
            SELECT * FROM changes
            WHERE change_seq > ?
            ORDER BY change_seq
            LIMIT ?
            """,
            (after_value, limit),
        ).fetchall()
    if kind == "snapshot":
        primary = 0 if after is None else _positive_int(after.primary)
        secondary = "" if after is None else after.secondary
        return database.execute(
            """
            SELECT * FROM snapshots
            WHERE (generation, snapshot_id) > (?, ?)
            ORDER BY generation, snapshot_id
            LIMIT ?
            """,
            (primary, secondary, limit),
        ).fetchall()
    at = 0.0 if after is None else float(after.primary)
    operation_id = "" if after is None else after.secondary
    return database.execute(
        """
        SELECT 'reset' AS operation, reset_id AS operation_id,
               snapshot_id, reason, assertions, transaction_id, at
        FROM knowledge_resets
        WHERE (at, reset_id) > (?, ?)
        UNION ALL
        SELECT 'restore' AS operation, restore_id AS operation_id,
               snapshot_id, reason, assertions, transaction_id, at
        FROM restores
        WHERE (at, restore_id) > (?, ?)
        ORDER BY at, operation_id
        LIMIT ?
        """,
        (at, operation_id, at, operation_id, limit),
    ).fetchall()


def _knowledge_items(
    database: sqlite3.Connection,
    player_id: str,
    kind: KnowledgeKind,
    rows: list[sqlite3.Row],
) -> tuple[tuple[KnowledgeItem, ...], bool]:
    items: list[KnowledgeItem] = []
    truncated = False
    for row in rows:
        values = dict(row)
        evidence: list[sqlite3.Row] = []
        source_refs: tuple[str, ...] = ("knowledge.db",)
        if kind == "assertion":
            evidence = database.execute(
                """
                SELECT *
                FROM evidence_refs
                WHERE assertion_id = ?
                ORDER BY observed_at, evidence_id
                LIMIT 33
                """,
                (row["assertion_id"],),
            ).fetchall()
            if len(evidence) > 32:
                truncated = True
            values["value"] = json.loads(str(values.pop("value_json")))
            values["evidence"] = [dict(item) for item in evidence[:32]]
            source_refs = tuple(
                f"session:{item['session_id']}:gateway:{item['source_seq']}"
                for item in evidence[:32]
            ) or ("knowledge.db",)
        sanitized, values_were_truncated = bounded_json_object(
            _sanitized_object(values),
            max_bytes=2_048,
        )
        truncated = truncated or values_were_truncated
        items.append(
            KnowledgeItem(
                id=_knowledge_id(kind, row),
                kind=kind,
                values=sanitized,
                source_refs=source_refs,
                evidence_continuation_cursor=(
                    encode_cursor(
                        CursorCoordinates(
                            resource=(
                                f"knowledge:{player_id}:assertion:"
                                f"{row['assertion_id']}:evidence"
                            ),
                            primary=str(int(evidence[31]["evidence_id"])),
                            secondary="",
                        )
                    )
                    if len(evidence) > 32
                    else None
                ),
            )
        )
    return tuple(items), truncated


def _knowledge_id(kind: KnowledgeKind, row: sqlite3.Row) -> str:
    if kind == "assertion":
        return str(row["assertion_id"])
    if kind == "change":
        return str(row["change_seq"])
    if kind == "snapshot":
        return str(row["snapshot_id"])
    return str(row["operation_id"])


def _knowledge_cursor(
    resource_id: str,
    kind: KnowledgeKind,
    row: sqlite3.Row,
) -> str:
    if kind == "assertion":
        primary, secondary = str(row["assertion_id"]), ""
    elif kind == "change":
        primary, secondary = str(row["change_seq"]), ""
    elif kind == "snapshot":
        primary, secondary = str(row["generation"]), str(row["snapshot_id"])
    else:
        primary, secondary = str(row["at"]), str(row["operation_id"])
    return encode_cursor(
        CursorCoordinates(
            resource=resource_id,
            primary=primary,
            secondary=secondary,
        )
    )


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError("knowledge cursor is invalid") from error
    if result < 0:
        raise ValueError("knowledge cursor is invalid")
    return result


def _sanitized_object(value: object) -> dict[str, Any]:
    sanitized = sanitize_evidence(value)
    if not isinstance(sanitized, dict):
        raise ResourceUnavailableError("knowledge evidence is not an object")
    return sanitized


_PLAYER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)
