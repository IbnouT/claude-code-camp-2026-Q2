"""Bounded launcher session catalog reads."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..database import open_readonly_database
from ..errors import MalformedSourceError
from ..models import SessionRecord
from .registry import SESSION_COLUMNS, RegistryDatabase


class SessionCatalogRepository:
    """Read lightweight session pages without hydrating retained evidence."""

    def __init__(self, registry: RegistryDatabase) -> None:
        self.registry = registry

    def page(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[SessionRecord, ...]:
        """Read one bounded catalog page ordered by current relevance."""
        if offset < 0:
            raise ValueError("catalog offset cannot be negative")
        if not 1 <= limit <= 500:
            raise ValueError("catalog limit must be between 1 and 500")
        columns = ", ".join(SESSION_COLUMNS)
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    f"""
                    SELECT {columns}
                    FROM sessions
                    ORDER BY
                      CASE state
                        WHEN 'running' THEN 0
                        WHEN 'starting' THEN 1
                        WHEN 'draining' THEN 2
                        WHEN 'quarantined' THEN 3
                        ELSE 4
                      END,
                      created_at DESC,
                      session_id
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "session catalog cannot be read",
            ) from error
        return tuple(self.registry.session_record(row) for row in rows)

    @staticmethod
    def journal_summary(record: SessionRecord) -> tuple[int, int]:
        """Return one session's current event count and latest sequence.

        Read from the session's own journal so the roster shows the true turn
        position even before the index has materialized the session.
        """
        journal = record.session_dir / "gateway.db"
        if not journal.is_file():
            return 0, 0
        try:
            with open_readonly_database(journal) as database:
                row = database.execute(
                    "SELECT COUNT(*) AS count, "
                    "COALESCE(MAX(seq), 0) AS latest FROM events"
                ).fetchone()
        except (sqlite3.Error, MalformedSourceError):
            return 0, 0
        return int(row["count"]), int(row["latest"])

    @staticmethod
    def objective_summary(
        record: SessionRecord,
    ) -> tuple[str | None, int | None, int | None]:
        """Return one session's current objective and its version count.

        The objective lives in the agent's own retained files, not in the
        gateway journal. Versions replay chronologically: the authored
        initial in ``agent.jsonl``, each applied operator revision, and
        every turn instruction that introduced a goal no earlier version
        stated. The newest turn instruction is the current objective.
        """
        initial, turns = _goal_statements(record.session_dir / "agent.jsonl")
        revisions, nudges = _operator_messages(
            record.session_dir / "operator-messages.json"
        )
        known: list[str] = []
        if initial is not None:
            known.append(initial)
        known.extend(revisions)
        goal_count = len(known)
        for instruction in turns:
            if instruction not in known:
                known.append(instruction)
                goal_count += 1
        objective = (
            turns[-1] if turns else revisions[-1] if revisions else initial
        )
        return objective, goal_count, nudges

    def live_player_ids(self) -> frozenset[str]:
        """Return every player id with an active session, across all pages.

        The launcher's ``start_available`` must be authoritative, not limited to
        one catalog page, so this reads the full live set from the registry.
        """
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    "SELECT DISTINCT player_id FROM sessions "
                    "WHERE state IN ('starting', 'running', 'draining', 'quarantined')"
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "live players cannot be read",
            ) from error
        return frozenset(str(row[0]) for row in rows)

    def keyset_page(
        self,
        *,
        after_created_at: str | None = None,
        after_session_id: str | None = None,
        player_id: str | None = None,
        limit: int = 50,
    ) -> tuple[SessionRecord, ...]:
        """Read one stable recent page without OFFSET."""
        if not 1 <= limit <= 51:
            raise ValueError("catalog limit must be between 1 and 51")
        if (after_created_at is None) != (after_session_id is None):
            raise ValueError("catalog cursor coordinates must be complete")
        columns = ", ".join(SESSION_COLUMNS)
        clauses: list[str] = []
        arguments: list[object] = []
        if player_id is not None:
            clauses.append("player_id = ?")
            arguments.append(player_id)
        if after_created_at is not None:
            clauses.append("(created_at, session_id) < (?, ?)")
            arguments.extend((after_created_at, after_session_id))
        where = "" if not clauses else f"WHERE {' AND '.join(clauses)}"
        arguments.append(limit)
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    f"""
                    SELECT {columns}
                    FROM sessions
                    {where}
                    ORDER BY created_at DESC, session_id DESC
                    LIMIT ?
                    """,
                    arguments,
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "session catalog cannot be read",
            ) from error
        return tuple(self.registry.session_record(row) for row in rows)


def _goal_statements(source: Path) -> tuple[str | None, list[str]]:
    """Read the authored objective and every turn instruction, in order."""
    if not source.is_file():
        return None, []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, []
    initial: str | None = None
    turns: list[str] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("phase") == "session_start" and initial is None:
            value = event.get("objective")
            title = value.get("title") if isinstance(value, dict) else None
            if isinstance(title, str) and title.strip():
                initial = title.strip()
        if event.get("phase") == "turn":
            instruction = event.get("instruction")
            if isinstance(instruction, str) and instruction.strip():
                turns.append(instruction.strip())
    return initial, turns


def _operator_messages(source: Path) -> tuple[list[str], int]:
    """Return applied revise instructions in order and the guide count."""
    if not source.is_file():
        return [], 0
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], 0
    raw = value.get("messages") if isinstance(value, dict) else None
    if not isinstance(raw, list):
        return [], 0
    messages = [
        message
        for message in raw
        if isinstance(message, dict)
        and isinstance(message.get("instruction"), str)
        and message.get("action") in {"guide", "revise"}
        and isinstance(message.get("applied_at"), str)
    ]
    revisions = [
        str(message["instruction"]).strip()
        for message in messages
        if message.get("action") == "revise"
        and str(message["instruction"]).strip()
    ]
    nudges = sum(message.get("action") == "guide" for message in messages)
    return revisions, nudges
