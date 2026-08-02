"""Validated launcher registry identity and row conversion."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..database import validate_database_schema
from ..errors import MalformedSourceError
from ..identity import validate_session_directory
from ..models import SessionRecord

REGISTRY_SCHEMA_VERSION = 1
SESSION_COLUMNS = (
    "session_id",
    "player_id",
    "character",
    "agent_id",
    "gateway_session_id",
    "experiment_id",
    "run_id",
    "session_dir",
    "manifest_path",
    "control_socket",
    "state",
    "pid",
    "created_at",
    "updated_at",
    "ended_at",
    "exit_code",
    "stop_mode",
    "capture_status",
    "legacy",
)
REQUIRED_REGISTRY_COLUMNS = {
    "sessions": frozenset(SESSION_COLUMNS),
    "lifecycle": frozenset({"id", "session_id", "at", "state", "detail"}),
}


class RegistryDatabase:
    """Validate one launcher-owned registry and convert its session rows."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir.expanduser().resolve()
        self.source = self.config_dir / "registry.db"
        validate_database_schema(
            self.source,
            expected_version=REGISTRY_SCHEMA_VERSION,
            required_columns=REQUIRED_REGISTRY_COLUMNS,
        )

    def session_record(self, row: Sequence[object]) -> SessionRecord:
        """Convert one validated registry row to a typed source record."""
        values = dict(zip(SESSION_COLUMNS, row, strict=True))
        session_id = _required_text(values, "session_id", self.source)
        player_id = _required_text(values, "player_id", self.source)
        session_dir = Path(_required_text(values, "session_dir", self.source))
        manifest_path = Path(_required_text(values, "manifest_path", self.source))
        canonical_dir = validate_session_directory(
            self.config_dir,
            player_id=player_id,
            session_id=session_id,
            session_dir=session_dir,
            manifest_path=manifest_path,
        )
        return SessionRecord(
            session_id=session_id,
            player_id=player_id,
            character=_required_text(values, "character", self.source),
            agent_id=_required_text(values, "agent_id", self.source),
            gateway_session_id=_required_text(
                values,
                "gateway_session_id",
                self.source,
            ),
            experiment_id=_optional_text(values["experiment_id"]),
            run_id=_optional_text(values["run_id"]),
            session_dir=canonical_dir,
            manifest_path=canonical_dir / "session.json",
            control_socket=Path(_required_text(values, "control_socket", self.source)),
            state=_required_text(values, "state", self.source),
            pid=_optional_int(values["pid"]),
            created_at=_required_text(values, "created_at", self.source),
            updated_at=_required_text(values, "updated_at", self.source),
            ended_at=_optional_text(values["ended_at"]),
            exit_code=_optional_int(values["exit_code"]),
            stop_mode=_optional_text(values["stop_mode"]),
            capture_status=_required_text(
                values,
                "capture_status",
                self.source,
            ),
            legacy=bool(values["legacy"]),
        )


def _required_text(
    values: dict[str, object],
    field: str,
    source: Path,
) -> str:
    value = values[field]
    if not isinstance(value, str) or not value:
        raise MalformedSourceError(source, f"{field} must be non-empty text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise TypeError("optional integer field must be an integer")
    return value
