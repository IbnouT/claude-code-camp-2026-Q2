"""Read one explicitly correlated benchmark sample as recorded session evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import RecordedSessionCatalogItem
from ..redaction import sanitize_evidence
from .benchmark import stable_run_id


@dataclass(frozen=True)
class GatewayEvidenceRow:
    """One sanitized gateway journal row."""

    sequence: int
    session: str
    at: float
    kind: str
    trace_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class RecordedSessionBundle:
    """Raw retained inputs for one explicitly linked experiment sample."""

    run_id: str
    ledger_name: str
    attempt_id: str
    record: dict[str, Any]
    agent_rows: tuple[dict[str, Any], ...]
    gateway_rows: tuple[GatewayEvidenceRow, ...]
    gateway_database: Path


class RecordedSessionSource:
    """Resolve public run IDs without exposing the runtime filesystem."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def catalog(self) -> tuple[RecordedSessionCatalogItem, ...]:
        """List only runs with an explicit attempt-ledger relationship."""

        items: list[RecordedSessionCatalogItem] = []
        if not self.root.is_dir():
            return ()
        for ledger in sorted(self.root.glob("*/attempts.jsonl")):
            if not _inside(ledger, self.root):
                continue
            for record in _json_lines(ledger):
                attempt = str(record.get("attempt_id", ""))
                if not attempt:
                    continue
                journey = str(record.get("journey_id", "unknown"))
                mode = str(record.get("result_mode", "unknown"))
                items.append(
                    RecordedSessionCatalogItem(
                        id=stable_run_id(ledger.parent.name, attempt),
                        source_kind="experiment_sample",
                        player_id=_player_id(record.get("profile_id")),
                        gateway_session_id=_gateway_session_id(
                            ledger.parent / "attempts" / attempt / "gateway.db"
                        ),
                        label=f"{journey} · {mode} · {attempt}",
                        journey=journey,
                        attempt=attempt,
                        success=bool(record.get("success", False)),
                        stop_reason=str(record.get("stop_reason", "unknown")),
                        iterations=int(record.get("iterations", 0) or 0),
                        cost_usd=float(record.get("cost_usd", 0) or 0),
                        result_mode=mode,
                    )
                )
        return tuple(sorted(items, key=lambda item: item.attempt, reverse=True))

    def load(self, run_id: str) -> RecordedSessionBundle | None:
        """Load one run only when its ledger and attempt stay below the root."""

        if not self.root.is_dir():
            return None
        for ledger in sorted(self.root.glob("*/attempts.jsonl")):
            if not _inside(ledger, self.root):
                continue
            for record in _json_lines(ledger):
                attempt_id = str(record.get("attempt_id", ""))
                if not attempt_id:
                    continue
                candidate = stable_run_id(ledger.parent.name, attempt_id)
                if candidate != run_id:
                    continue
                attempt = ledger.parent / "attempts" / attempt_id
                agent_path = attempt / "agent.jsonl"
                gateway_path = attempt / "gateway.db"
                agent_rows = (
                    tuple(_json_lines(agent_path))
                    if _inside(agent_path, self.root)
                    else ()
                )
                gateway_rows = (
                    _gateway_rows(gateway_path)
                    if _inside(gateway_path, self.root)
                    else ()
                )
                return RecordedSessionBundle(
                    run_id=run_id,
                    ledger_name=ledger.parent.name,
                    attempt_id=attempt_id,
                    record=sanitize_evidence(record),
                    agent_rows=tuple(sanitize_evidence(row) for row in agent_rows),
                    gateway_rows=gateway_rows,
                    gateway_database=gateway_path,
                )
        return None


def _json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _gateway_rows(path: Path) -> tuple[GatewayEvidenceRow, ...]:
    if not path.is_file():
        return ()
    connection = sqlite3.connect(
        f"file:{path.resolve()}?mode=ro",
        uri=True,
    )
    try:
        rows = connection.execute(
            "SELECT seq, session, at, kind, trace_id, payload FROM events ORDER BY seq"
        ).fetchall()
    except sqlite3.DatabaseError:
        return ()
    finally:
        connection.close()
    result: list[GatewayEvidenceRow] = []
    for sequence, session, at, kind, trace_id, encoded in rows:
        try:
            payload = json.loads(encoded)
        except (json.JSONDecodeError, TypeError):
            payload = {"capture_gap": "Gateway payload is not valid JSON"}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        result.append(
            GatewayEvidenceRow(
                sequence=int(sequence),
                session=str(session),
                at=float(at),
                kind=str(kind),
                trace_id=str(trace_id) if trace_id else None,
                payload=sanitize_evidence(payload),
            )
        )
    return tuple(result)


def _gateway_session_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(
            f"file:{path.resolve()}?mode=ro",
            uri=True,
        ) as connection:
            row = connection.execute(
                "SELECT session FROM events ORDER BY seq LIMIT 1"
            ).fetchone()
    except sqlite3.DatabaseError:
        return None
    return str(row[0]) if row is not None else None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _player_id(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return "unattributed"
