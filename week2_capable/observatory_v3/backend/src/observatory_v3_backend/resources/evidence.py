"""Bounded evidence, trace, wire, cost, and search resources."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from hashlib import sha256
from typing import cast

from ..database import open_readonly_database
from ..redaction import sanitize_evidence
from .base import (
    ResourceBase,
    ResourceNotFoundError,
    ResourceUnavailableError,
    cursor_int,
    decode_payload,
    entity_summary,
    first_text,
    json_object,
    validate_limit,
)
from .bounds import bounded_json_object
from .content import value_chunk
from .contracts import (
    CostContributor,
    CostRangeResponse,
    EntityKind,
    EvidenceRecordResponse,
    SearchMatch,
    SearchPageResponse,
    TracePageResponse,
    TraceRecord,
    ValueChunkResponse,
    WireBodyResponse,
)
from .cursor import CursorCoordinates, decode_cursor, encode_cursor

MAX_WIRE_BODY_BYTES = 65_536
MAX_EVIDENCE_FIELDS_BYTES = 220 * 1024


class EvidenceResources(ResourceBase):
    """Read one bounded evidence or economics view at a time."""

    def evidence_record(
        self,
        session_id: str,
        record_id: str,
    ) -> EvidenceRecordResponse:
        with closing(self._connect()) as database:
            row = database.execute(
                """
                SELECT e.*, p.evidence_kind, p.trace_id, p.payload,
                       p.integrity_digest, p.duration_ms, p.tokens, p.cost_usd
                FROM entities AS e
                JOIN evidence_payloads AS p ON p.entity_id = e.id
                WHERE e.session_id = ? AND e.id = ?
                """,
                (session_id, record_id),
            ).fetchone()
            related = database.execute(
                """
                SELECT id FROM entities
                WHERE session_id = ?
                  AND (parent_id = ? OR goal_id = ? OR turn_id = ?
                       OR iteration_id = ?) AND id != ?
                ORDER BY ordinal, id LIMIT 101
                """,
                (session_id, record_id, record_id, record_id, record_id, record_id),
            ).fetchall()
        if row is None:
            raise ResourceNotFoundError(record_id)
        fields, truncated = bounded_json_object(
            decode_payload(row["payload"]),
            max_bytes=MAX_EVIDENCE_FIELDS_BYTES,
        )
        ancestry = tuple(
            dict.fromkeys(
                str(value)
                for value in (
                    row["parent_id"],
                    row["goal_id"],
                    row["turn_id"],
                    row["iteration_id"],
                )
                if value is not None and str(value) != record_id
            )
        )
        gaps = (
            *(("related_ids_truncated",) if len(related) > 100 else ()),
            *(("evidence_fields_truncated",) if truncated else ()),
        )
        return EvidenceRecordResponse(
            **self._metadata(
                session_id,
                f"evidence:{record_id}",
                gaps=gaps,
                refs=(str(row["source_ref"]), "observatory index evidence"),
            ),
            record=entity_summary(row),
            evidence_kind=str(row["evidence_kind"]),
            trace_id=None if row["trace_id"] is None else str(row["trace_id"]),
            integrity_digest=str(row["integrity_digest"]),
            fields=fields,
            ancestry=ancestry,
            related_ids=tuple(str(item["id"]) for item in related[:100]),
        )

    def evidence_content(
        self,
        session_id: str,
        record_id: str,
        *,
        offset: int,
        max_bytes: int,
    ) -> ValueChunkResponse:
        """Expose every sanitized retained field through bounded exact chunks."""
        with closing(self._connect()) as database:
            row = database.execute(
                """
                SELECT e.source_ref, p.payload
                FROM entities AS e
                JOIN evidence_payloads AS p ON p.entity_id = e.id
                WHERE e.session_id = ? AND e.id = ?
                """,
                (session_id, record_id),
            ).fetchone()
        if row is None:
            raise ResourceNotFoundError(record_id)
        return value_chunk(
            json_object(sanitize_evidence(decode_payload(row["payload"]))),
            metadata=self._metadata(
                session_id,
                f"evidence:{record_id}:content",
                refs=(str(row["source_ref"]), "observatory index evidence"),
            ),
            offset=offset,
            max_bytes=max_bytes,
        )

    def trace_page(
        self,
        session_id: str,
        trace_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> TracePageResponse:
        validate_limit(limit, maximum=100)
        resource_id = f"session:{session_id}:trace:{trace_id}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        clauses = ["e.session_id = ?", "p.trace_id = ?"]
        arguments: list[object] = [session_id, trace_id]
        if after is not None:
            clauses.append("(e.ordinal, e.id) > (?, ?)")
            arguments.extend((cursor_int(after.primary), after.secondary))
        arguments.append(limit + 1)
        with closing(self._connect()) as database:
            rows = database.execute(
                f"""
                SELECT e.*, p.evidence_kind, p.duration_ms, p.tokens, p.cost_usd
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE {" AND ".join(clauses)}
                ORDER BY e.ordinal, e.id LIMIT ?
                """,
                arguments,
            ).fetchall()
        if not rows and cursor is None:
            raise ResourceNotFoundError(trace_id)
        items = tuple(
            TraceRecord(
                record=entity_summary(row),
                evidence_kind=str(row["evidence_kind"]),
            )
            for row in rows[:limit]
        )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(items[-1].record.ordinal),
                    secondary=items[-1].record.id,
                )
            )
            if len(rows) > limit and items
            else None
        )
        return TracePageResponse(
            **self._metadata(
                session_id,
                f"trace:{trace_id}",
                refs=("gateway.db trace", "observatory index evidence"),
            ),
            trace_id=trace_id,
            continuation_cursor=continuation,
            items=items,
        )

    def wire_body(
        self,
        session_id: str,
        digest: str,
        *,
        max_bytes: int,
    ) -> WireBodyResponse:
        if not 1 <= max_bytes <= MAX_WIRE_BODY_BYTES:
            raise ValueError("wire max_bytes must be between 1 and 65536")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("wire digest must be lowercase SHA-256")
        source = self._session_source(session_id) / "gateway.db"
        try:
            with open_readonly_database(source) as database:
                row = database.execute(
                    "SELECT rowid, length(body) AS size FROM blobs WHERE digest = ?",
                    (digest,),
                ).fetchone()
                if row is None:
                    raise ResourceNotFoundError(digest)
                blob = database.blobopen(
                    "blobs",
                    "body",
                    int(row["rowid"]),
                    readonly=True,
                )
                try:
                    hasher = sha256()
                    retained = bytearray()
                    for chunk in _blob_chunks(blob):
                        hasher.update(chunk)
                        if len(retained) <= max_bytes:
                            retained.extend(chunk[: max_bytes + 1 - len(retained)])
                finally:
                    blob.close()
        except sqlite3.Error as error:
            raise ResourceUnavailableError("wire body cannot be read") from error
        if hasher.hexdigest() != digest:
            raise ResourceUnavailableError("wire body integrity check failed")
        decoded = bytes(retained[:max_bytes]).decode("utf-8", errors="replace")
        sanitized = sanitize_evidence(decoded)
        text = sanitized if isinstance(sanitized, str) else ""
        bounded = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        return WireBodyResponse(
            **self._metadata(
                session_id,
                f"wire:{digest}",
                refs=(f"gateway.db blob {digest}",),
            ),
            digest=digest,
            media_type="text/plain; charset=utf-8",
            byte_length=len(bounded.encode()),
            truncated=len(retained) > max_bytes or bounded != text,
            body=bounded,
            redacted=bounded != decoded,
        )

    def cost_range(
        self,
        session_id: str,
        *,
        scope_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> CostRangeResponse:
        validate_limit(limit, maximum=100)
        if scope_id is not None:
            self._require_entity(session_id, scope_id)
        scope = scope_id or session_id
        resource_id = f"session:{session_id}:cost:{scope}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        clauses = [
            "e.session_id = ?",
            "e.kind = 'record'",
            "(p.cost_usd IS NOT NULL OR p.tokens IS NOT NULL)",
        ]
        arguments: list[object] = [session_id]
        if scope_id is not None:
            clauses.append(
                "(e.id = ? OR e.goal_id = ? OR e.turn_id = ? OR e.iteration_id = ?)"
            )
            arguments.extend((scope_id, scope_id, scope_id, scope_id))
        total_clauses, total_arguments = tuple(clauses), tuple(arguments)
        if after is not None:
            clauses.append("(e.ordinal, e.id) > (?, ?)")
            arguments.extend((cursor_int(after.primary), after.secondary))
        arguments.append(limit + 1)
        with closing(self._connect()) as database:
            totals = database.execute(
                f"""
                SELECT COALESCE(SUM(p.tokens), 0) AS tokens,
                       COALESCE(SUM(p.cost_usd), 0) AS cost,
                       COALESCE(SUM(p.duration_ms), 0) AS duration
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE {" AND ".join(total_clauses)}
                """,
                total_arguments,
            ).fetchone()
            rows = database.execute(
                f"""
                SELECT e.id, e.occurred_at, e.ordinal, e.source_ref, p.*
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE {" AND ".join(clauses)}
                ORDER BY e.ordinal, e.id LIMIT ?
                """,
                arguments,
            ).fetchall()
        contributors = tuple(_contributor(row) for row in rows[:limit])
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(int(rows[limit - 1]["ordinal"])),
                    secondary=str(rows[limit - 1]["id"]),
                )
            )
            if len(rows) > limit and contributors
            else None
        )
        return CostRangeResponse(
            **self._metadata(
                session_id,
                f"cost:{scope}",
                refs=("agent.jsonl usage", "observatory index evidence"),
            ),
            scope_id=scope,
            total_tokens=0 if totals is None else int(totals["tokens"]),
            total_cost_usd=0.0 if totals is None else float(totals["cost"]),
            total_duration_ms=0.0 if totals is None else float(totals["duration"]),
            continuation_cursor=continuation,
            contributors=contributors,
        )

    def search_page(
        self,
        session_id: str,
        *,
        query: str,
        cursor: str | None,
        limit: int,
    ) -> SearchPageResponse:
        validate_limit(limit, maximum=50)
        tokens = [token[:128] for token in query.split() if token][:32]
        if not tokens:
            raise ValueError("search query must contain at least one word")
        expression = " AND ".join(
            f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens
        )
        query_digest = sha256(query.encode()).hexdigest()
        resource_id = f"session:{session_id}:search:{query_digest}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        clauses = ["search_fts MATCH ?", "d.session_id = ?"]
        arguments: list[object] = [expression, session_id]
        if after is not None:
            clauses.append("(d.occurred_at, d.entity_id) > (?, ?)")
            arguments.extend((after.primary, after.secondary))
        arguments.append(limit + 1)
        with closing(self._connect()) as database:
            rows = database.execute(
                f"""
                SELECT d.* FROM search_fts
                JOIN search_documents AS d ON d.rowid = search_fts.rowid
                WHERE {" AND ".join(clauses)}
                ORDER BY d.occurred_at, d.entity_id LIMIT ?
                """,
                arguments,
            ).fetchall()
        matches = tuple(
            SearchMatch(
                record_id=str(row["entity_id"]),
                kind=cast(EntityKind, str(row["kind"])),
                occurred_at=str(row["occurred_at"]),
                title=str(row["title"]),
                excerpt=str(row["body"]),
            )
            for row in rows[:limit]
        )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=matches[-1].occurred_at,
                    secondary=matches[-1].record_id,
                )
            )
            if len(rows) > limit and matches
            else None
        )
        return SearchPageResponse(
            **self._metadata(
                session_id,
                "search",
                refs=("observatory index sanitized search",),
            ),
            query=query,
            continuation_cursor=continuation,
            matches=matches,
        )


def _contributor(row: sqlite3.Row) -> CostContributor:
    payload = decode_payload(row["payload"])
    model = first_text(payload, ("model",))
    nested = payload.get("payload")
    if model is None and isinstance(nested, dict):
        model = first_text(nested, ("model",))
    return CostContributor(
        record_id=str(row["id"]),
        occurred_at=str(row["occurred_at"]),
        model=(
            None
            if model is None
            else model.encode("utf-8")[:256].decode("utf-8", errors="ignore")
        ),
        tokens=0 if row["tokens"] is None else int(row["tokens"]),
        cost_usd=0.0 if row["cost_usd"] is None else float(row["cost_usd"]),
        duration_ms=0.0 if row["duration_ms"] is None else float(row["duration_ms"]),
        source_ref=str(row["source_ref"]),
    )


def _blob_chunks(blob: sqlite3.Blob, *, size: int = 16_384) -> Iterator[bytes]:
    while True:
        chunk = blob.read(size)
        if not chunk:
            return
        yield chunk
