"""Bounded session summaries and hierarchy pages."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Literal

from ..database import open_readonly_database
from ..index.store import IndexCorruptionError
from ..redaction import sanitize_evidence
from ..repositories import LifecycleRepository
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
from .bounds import bounded_json_object, bounded_text
from .content import value_chunk
from .contracts import (
    EntityPageResponse,
    EntitySummary,
    GoalPageResponse,
    GoalResource,
    LifecyclePageResponse,
    LifecycleSummary,
    SessionSummaryResponse,
    SessionTotals,
    TurnPageResponse,
    TurnResource,
    ValueChunkResponse,
)
from .cursor import CursorCoordinates, decode_cursor, encode_cursor

MAX_LIFECYCLE_DETAIL_BYTES = 2_048
MAX_OUTCOME_BYTES = 2_048
MAX_REGISTRY_LABEL_BYTES = 512


class SessionResources(ResourceBase):
    """Read session identity, lifecycle, and hierarchy resources."""

    def session_summary(self, session_id: str) -> SessionSummaryResponse:
        checkpoint = self.index.checkpoint(session_id)
        if checkpoint is None:
            raise ResourceNotFoundError(session_id)
        with closing(self._connect()) as database:
            session = database.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            totals = database.execute(
                """
                SELECT COALESCE(SUM(p.tokens), 0) AS tokens,
                       COALESCE(SUM(p.cost_usd), 0) AS cost_usd,
                       COALESCE(SUM(p.duration_ms), 0) AS duration_ms
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE p.session_id = ? AND e.kind = 'record'
                """,
                (session_id,),
            ).fetchone()
        if session is None or totals is None:
            raise IndexCorruptionError(f"session {session_id!r} is incomplete")

        lifecycle = LifecycleRepository(self.registry).latest_page(
            session_id,
            limit=33,
        )
        lifecycle_truncated = len(lifecycle) > 32
        lifecycle_items: list[LifecycleSummary] = []
        lifecycle_detail_truncated = False
        for record in lifecycle[-32:]:
            detail, truncated = bounded_json_object(
                json_object(sanitize_evidence(record.detail)),
                max_bytes=MAX_LIFECYCLE_DETAIL_BYTES,
            )
            lifecycle_detail_truncated = lifecycle_detail_truncated or truncated
            lifecycle_items.append(
                LifecycleSummary(
                    sequence=record.sequence,
                    at=record.at,
                    state=record.state,
                    detail=detail,
                )
            )
        gaps = list(checkpoint.capture_gaps)
        if lifecycle_truncated:
            gaps.append("lifecycle_summary_truncated")
        if lifecycle_detail_truncated:
            gaps.append("lifecycle_detail_truncated")
        character, character_truncated = bounded_text(
            str(session["character"]),
            max_bytes=MAX_REGISTRY_LABEL_BYTES,
        )
        if character_truncated:
            gaps.append("registry_character_truncated")
        latest_goal = (
            None if session["latest_goal"] is None else str(session["latest_goal"])
        )
        if latest_goal is not None:
            latest_goal, latest_goal_truncated = bounded_text(
                latest_goal,
                max_bytes=MAX_REGISTRY_LABEL_BYTES,
            )
            if latest_goal_truncated:
                gaps.append("registry_latest_goal_truncated")
        return SessionSummaryResponse(
            **self._metadata(
                session_id,
                "summary",
                gaps=tuple(gaps),
                refs=(
                    "registry.db sessions",
                    "registry.db lifecycle",
                    "observatory index",
                ),
            ),
            session_id=session_id,
            player_id=str(session["player_id"]),
            character=character,
            state=str(session["state"]),
            created_at=str(session["created_at"]),
            updated_at=str(session["updated_at"]),
            ended_at=(
                None if session["ended_at"] is None else str(session["ended_at"])
            ),
            capture_status=str(session["capture_status"]),
            latest_goal_id=(
                None
                if session["latest_goal_id"] is None
                else str(session["latest_goal_id"])
            ),
            latest_goal=latest_goal,
            totals=SessionTotals(
                goals=int(session["goal_count"]),
                nudges=int(session["nudge_count"]),
                turns=int(session["turn_count"]),
                iterations=int(session["iteration_count"]),
                records=int(session["record_count"]),
                tokens=int(totals["tokens"]),
                cost_usd=float(totals["cost_usd"]),
                duration_ms=float(totals["duration_ms"]),
            ),
            lifecycle=tuple(lifecycle_items),
            lifecycle_cursor=(
                encode_cursor(
                    CursorCoordinates(
                        resource=f"session:{session_id}:lifecycle",
                        primary=str(lifecycle_items[0].sequence),
                        secondary="",
                    )
                )
                if lifecycle_truncated and lifecycle_items
                else None
            ),
            goal_cursor=None,
            search_cursor=None,
        )

    def lifecycle_page(
        self,
        session_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> LifecyclePageResponse:
        validate_limit(limit, maximum=100)
        resource_id = f"session:{session_id}:lifecycle"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        clauses = ["session_id = ?"]
        arguments: list[object] = [session_id]
        if after is not None:
            clauses.append("id < ?")
            arguments.append(cursor_int(after.primary))
        arguments.append(limit + 1)
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    f"""
                    SELECT id, at, state, detail
                    FROM lifecycle
                    WHERE {" AND ".join(clauses)}
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    arguments,
                ).fetchall()
        except sqlite3.Error as error:
            raise ResourceUnavailableError("lifecycle page cannot be read") from error
        if not rows and cursor is None:
            self._require_registered_session(session_id)
        visible = rows[:limit]
        detail_truncated = False
        items_list: list[LifecycleSummary] = []
        for row in reversed(visible):
            detail, truncated = bounded_json_object(
                json_object(sanitize_evidence(json.loads(str(row["detail"])))),
                max_bytes=MAX_LIFECYCLE_DETAIL_BYTES,
            )
            detail_truncated = detail_truncated or truncated
            items_list.append(
                LifecycleSummary(
                    sequence=int(row["id"]),
                    at=str(row["at"]),
                    state=str(row["state"]),
                    detail=detail,
                )
            )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(int(visible[-1]["id"])),
                    secondary="",
                )
            )
            if len(rows) > limit and visible
            else None
        )
        return LifecyclePageResponse(
            **self._metadata(
                session_id,
                "lifecycle",
                gaps=(("lifecycle_detail_truncated",) if detail_truncated else ()),
                refs=("registry.db lifecycle",),
            ),
            continuation_cursor=continuation,
            items=tuple(items_list),
        )

    def lifecycle_content(
        self,
        session_id: str,
        sequence: int,
        *,
        offset: int,
        max_bytes: int,
    ) -> ValueChunkResponse:
        """Expose one full sanitized lifecycle detail through bounded chunks."""
        if sequence < 1:
            raise ValueError("lifecycle sequence must be positive")
        try:
            with open_readonly_database(self.registry.source) as database:
                row = database.execute(
                    """
                    SELECT detail
                    FROM lifecycle
                    WHERE session_id = ? AND id = ?
                    """,
                    (session_id, sequence),
                ).fetchone()
        except sqlite3.Error as error:
            raise ResourceUnavailableError(
                "lifecycle content cannot be read"
            ) from error
        if row is None:
            raise ResourceNotFoundError(str(sequence))
        return value_chunk(
            json_object(sanitize_evidence(json.loads(str(row["detail"])))),
            metadata=self._metadata(
                session_id,
                f"lifecycle:{sequence}:content",
                refs=("registry.db lifecycle",),
            ),
            offset=offset,
            max_bytes=max_bytes,
        )

    def goal_page(
        self,
        session_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> GoalPageResponse:
        validate_limit(limit, maximum=20)
        page = self.entity_page(
            session_id,
            resource_kind="goals",
            scope_id=None,
            cursor=cursor,
            limit=limit,
        )
        with closing(self._connect()) as database:
            items = tuple(
                self._goal_resource(database, session_id, goal) for goal in page.items
            )
        return GoalPageResponse(
            **self._metadata(
                session_id,
                "goals:root",
                refs=("observatory index entities", "observatory index evidence"),
            ),
            continuation_cursor=page.continuation_cursor,
            items=items,
        )

    def turn_page(
        self,
        session_id: str,
        goal_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> TurnPageResponse:
        validate_limit(limit, maximum=20)
        page = self.entity_page(
            session_id,
            resource_kind="turns",
            scope_id=goal_id,
            cursor=cursor,
            limit=limit,
        )
        with closing(self._connect()) as database:
            items = tuple(
                self._turn_resource(database, session_id, turn) for turn in page.items
            )
        return TurnPageResponse(
            **self._metadata(
                session_id,
                f"turns:{goal_id}",
                refs=("observatory index entities", "observatory index evidence"),
            ),
            continuation_cursor=page.continuation_cursor,
            items=items,
        )

    def entity_page(
        self,
        session_id: str,
        *,
        resource_kind: Literal["goals", "turns", "iterations", "children"],
        scope_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> EntityPageResponse:
        validate_limit(limit, maximum=100)
        resource_id = f"session:{session_id}:{resource_kind}:{scope_id or 'root'}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        clauses = ["e.session_id = ?"]
        arguments: list[object] = [session_id]
        if resource_kind == "goals":
            clauses.append("e.kind = 'goal'")
        elif resource_kind == "turns":
            identity = _required_scope(scope_id)
            self._require_entity(session_id, identity, "goal")
            clauses.extend(("e.kind = 'turn'", "e.goal_id = ?"))
            arguments.append(identity)
        elif resource_kind == "iterations":
            identity = _required_scope(scope_id)
            self._require_entity(session_id, identity, "turn")
            clauses.extend(("e.kind = 'iteration'", "e.turn_id = ?"))
            arguments.append(identity)
        else:
            identity = _required_scope(scope_id)
            self._require_entity(session_id, identity)
            clauses.append("e.parent_id = ?")
            arguments.append(identity)
        if after is not None:
            clauses.append("(e.ordinal, e.id) > (?, ?)")
            arguments.extend((cursor_int(after.primary), after.secondary))
        arguments.append(limit + 1)
        with closing(self._connect()) as database:
            rows = database.execute(
                f"""
                SELECT e.*, p.duration_ms, p.tokens, p.cost_usd
                FROM entities AS e
                LEFT JOIN evidence_payloads AS p ON p.entity_id = e.id
                WHERE {" AND ".join(clauses)}
                ORDER BY e.ordinal, e.id
                LIMIT ?
                """,
                arguments,
            ).fetchall()
        items = tuple(entity_summary(row) for row in rows[:limit])
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(items[-1].ordinal),
                    secondary=items[-1].id,
                )
            )
            if len(rows) > limit and items
            else None
        )
        return EntityPageResponse(
            **self._metadata(
                session_id,
                f"{resource_kind}:{scope_id or 'root'}",
                refs=("observatory index entities",),
            ),
            continuation_cursor=continuation,
            items=items,
        )

    def _goal_resource(
        self,
        database: sqlite3.Connection,
        session_id: str,
        goal: EntitySummary,
    ) -> GoalResource:
        children = self._owned_children(
            database,
            session_id,
            column="goal_id",
            identity=goal.id,
            kinds=("nudge", "turn"),
            limit=11,
        )
        visible, continuation_boundary = _lossless_goal_context(children)
        nudges = tuple(item for item in visible if item.kind == "nudge")
        turns = tuple(item for item in visible if item.kind == "turn")
        tokens, cost, duration, outcome = self._owned_usage(
            database,
            session_id,
            column="goal_id",
            identity=goal.id,
        )
        return GoalResource(
            goal=goal,
            nudges=nudges,
            turns=turns,
            outcome=outcome,
            tokens=tokens,
            cost_usd=cost,
            duration_ms=duration,
            child_continuation_cursor=(
                encode_cursor(
                    CursorCoordinates(
                        resource=f"session:{session_id}:children:{goal.id}",
                        primary=str(continuation_boundary.ordinal),
                        secondary=continuation_boundary.id,
                    )
                )
                if continuation_boundary is not None
                else None
            ),
        )

    def _turn_resource(
        self,
        database: sqlite3.Connection,
        session_id: str,
        turn: EntitySummary,
    ) -> TurnResource:
        iterations = self._owned_children(
            database,
            session_id,
            column="turn_id",
            identity=turn.id,
            kinds=("iteration",),
            limit=11,
        )
        tokens, cost, duration, outcome = self._owned_usage(
            database,
            session_id,
            column="turn_id",
            identity=turn.id,
        )
        return TurnResource(
            turn=turn,
            iterations=iterations[:10],
            outcome=outcome,
            tokens=tokens,
            cost_usd=cost,
            duration_ms=duration,
            child_continuation_cursor=(
                encode_cursor(
                    CursorCoordinates(
                        resource=f"session:{session_id}:iterations:{turn.id}",
                        primary=str(iterations[9].ordinal),
                        secondary=iterations[9].id,
                    )
                )
                if len(iterations) > 10
                else None
            ),
        )

    def _owned_children(
        self,
        database: sqlite3.Connection,
        session_id: str,
        *,
        column: Literal["goal_id", "turn_id"],
        identity: str,
        kinds: tuple[str, ...],
        limit: int,
    ) -> tuple[EntitySummary, ...]:
        placeholders = ",".join("?" for _ in kinds)
        rows = database.execute(
            f"""
            SELECT e.*, p.duration_ms, p.tokens, p.cost_usd
            FROM entities AS e
            LEFT JOIN evidence_payloads AS p ON p.entity_id = e.id
            WHERE e.session_id = ? AND e.{column} = ?
              AND e.kind IN ({placeholders}) AND e.id != ?
            ORDER BY e.ordinal, e.id
            LIMIT ?
            """,
            (session_id, identity, *kinds, identity, limit),
        ).fetchall()
        return tuple(entity_summary(row) for row in rows)

    def _owned_usage(
        self,
        database: sqlite3.Connection,
        session_id: str,
        *,
        column: Literal["goal_id", "turn_id"],
        identity: str,
    ) -> tuple[int, float, float, str | None]:
        totals = database.execute(
            f"""
            SELECT COALESCE(SUM(p.tokens), 0) AS tokens,
                   COALESCE(SUM(p.cost_usd), 0) AS cost,
                   COALESCE(SUM(p.duration_ms), 0) AS duration
            FROM evidence_payloads AS p
            JOIN entities AS e ON e.id = p.entity_id
            WHERE e.session_id = ? AND e.{column} = ? AND e.kind = 'record'
            """,
            (session_id, identity),
        ).fetchone()
        outcome_row = database.execute(
            f"""
            SELECT p.payload
            FROM evidence_payloads AS p
            JOIN entities AS e ON e.id = p.entity_id
            WHERE e.session_id = ? AND e.{column} = ?
              AND p.evidence_kind = 'agent:response'
            ORDER BY e.ordinal DESC, e.id DESC
            LIMIT 1
            """,
            (session_id, identity),
        ).fetchone()
        outcome = None
        if outcome_row is not None:
            outcome = first_text(
                decode_payload(outcome_row["payload"]),
                ("text", "response", "output"),
            )
            if outcome is not None:
                outcome = _bounded_text(outcome, MAX_OUTCOME_BYTES)
        return (
            0 if totals is None else int(totals["tokens"]),
            0.0 if totals is None else float(totals["cost"]),
            0.0 if totals is None else float(totals["duration"]),
            outcome,
        )

    def _require_registered_session(self, session_id: str) -> None:
        with open_readonly_database(self.registry.source) as database:
            row = database.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise ResourceNotFoundError(session_id)


def _required_scope(scope_id: str | None) -> str:
    if scope_id is None:
        raise ValueError("resource scope is required")
    return scope_id


def _bounded_text(value: str, maximum: int) -> str:
    return value.encode("utf-8")[:maximum].decode("utf-8", errors="ignore")


def _lossless_goal_context(
    children: tuple[EntitySummary, ...],
) -> tuple[tuple[EntitySummary, ...], EntitySummary | None]:
    """Clip at the first omitted child so the embedded cursor cannot skip it."""
    nudges = 0
    turns = 0
    visible: list[EntitySummary] = []
    for child in children[:10]:
        if child.kind == "nudge":
            if nudges >= 5:
                break
            nudges += 1
        elif child.kind == "turn":
            if turns >= 5:
                break
            turns += 1
        visible.append(child)
    if len(visible) < len(children):
        boundary = None if not visible else visible[-1]
        return tuple(visible), boundary
    return tuple(visible), None
