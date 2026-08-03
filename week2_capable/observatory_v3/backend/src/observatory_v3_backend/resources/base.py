"""Shared storage boundary and small helpers for bounded read repositories."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, cast

from ..database import open_readonly_database
from ..index.store import IndexCorruptionError, IndexStore
from ..materialization.cursor import CompositeSourceCursor
from ..repositories import RegistryDatabase
from .contracts import Completeness, EntityKind, EntitySummary


class ResourceNotFoundError(KeyError):
    """A bounded resource identity does not exist in the selected scope."""


class ResourceUnavailableError(RuntimeError):
    """A required retained source is unavailable."""


class ResourceBase:
    """Own shared read-only index and retained-source access."""

    def __init__(self, index: IndexStore, registry: RegistryDatabase) -> None:
        self.index = index
        self.registry = registry

    def _metadata(
        self,
        session_id: str,
        suffix: str,
        *,
        gaps: tuple[str, ...] = (),
        refs: tuple[str, ...],
    ) -> dict[str, Any]:
        checkpoint = self.index.checkpoint(session_id)
        if checkpoint is None:
            raise ResourceNotFoundError(session_id)
        all_gaps = tuple(dict.fromkeys((*checkpoint.capture_gaps, *gaps)))[:32]
        completeness: Completeness
        if checkpoint.capture_status == "fault":
            completeness = "degraded"
        elif all_gaps:
            completeness = "partial"
        else:
            completeness = "complete"
        return {
            "resource_id": f"session:{session_id}:{suffix}",
            "resource_version": checkpoint.generation,
            "source_cursor": CompositeSourceCursor.from_watermark(
                checkpoint.watermark
            ).token,
            "completeness": completeness,
            "capture_gaps": all_gaps,
            "source_refs": refs[:16],
        }

    def _require_entity(
        self,
        session_id: str,
        identity: str,
        kind: EntityKind | None = None,
    ) -> None:
        with closing(self._connect()) as database:
            row = database.execute(
                "SELECT kind FROM entities WHERE session_id = ? AND id = ?",
                (session_id, identity),
            ).fetchone()
        if row is None or (kind is not None and str(row["kind"]) != kind):
            raise ResourceNotFoundError(identity)

    def _session_source(self, session_id: str) -> Path:
        try:
            with open_readonly_database(self.registry.source) as database:
                row = database.execute(
                    "SELECT session_dir FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ResourceUnavailableError("session source cannot be read") from error
        if row is None:
            raise ResourceNotFoundError(session_id)
        path = Path(str(row["session_dir"])).resolve()
        expected = (self.registry.config_dir / "profiles").resolve()
        if expected not in path.parents:
            raise ResourceUnavailableError("session source escaped runtime root")
        return path

    def _connect(self) -> sqlite3.Connection:
        try:
            database = sqlite3.connect(
                f"{self.index.source.as_uri()}?mode=ro",
                uri=True,
                timeout=2.0,
            )
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA query_only=ON")
            database.execute("PRAGMA busy_timeout=2000")
            return database
        except sqlite3.Error as error:
            raise IndexCorruptionError("resource index cannot be read") from error


def entity_summary(row: sqlite3.Row) -> EntitySummary:
    return EntitySummary(
        id=str(row["id"]),
        kind=cast(EntityKind, str(row["kind"])),
        parent_id=None if row["parent_id"] is None else str(row["parent_id"]),
        goal_id=None if row["goal_id"] is None else str(row["goal_id"]),
        turn_id=None if row["turn_id"] is None else str(row["turn_id"]),
        iteration_id=(
            None if row["iteration_id"] is None else str(row["iteration_id"])
        ),
        ordinal=int(row["ordinal"]),
        occurred_at=str(row["occurred_at"]),
        title=str(row["title"]),
        source_ref=str(row["source_ref"]),
        duration_ms=(None if row["duration_ms"] is None else float(row["duration_ms"])),
        tokens=None if row["tokens"] is None else int(row["tokens"]),
        cost_usd=None if row["cost_usd"] is None else float(row["cost_usd"]),
    )


def validate_limit(limit: int, *, maximum: int) -> None:
    if not 1 <= limit <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")


def cursor_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError("cursor coordinate is not an integer") from error
    if result < 0:
        raise ValueError("cursor coordinate cannot be negative")
    return result


def decode_payload(value: object) -> dict[str, Any]:
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise IndexCorruptionError("indexed evidence payload is invalid") from error
    if not isinstance(decoded, dict):
        raise IndexCorruptionError("indexed evidence payload is not an object")
    return decoded


def json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("value is not a JSON object")
    return value


def first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None
