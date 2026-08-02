"""Public-safe control state derived from retained session identity."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from ..models import ControlStatus, SessionRecord


class ControlRepository:
    """Preserve current control discovery without exposing credentials."""

    def status(self, session: SessionRecord) -> ControlStatus:
        """Return effective state and authenticated operator availability."""
        return ControlStatus(
            state=self._effective_state(session.session_dir),
            available=self._operator_available(session),
        )

    @staticmethod
    def _effective_state(session_dir: Path) -> str | None:
        states: list[str] = []
        for name in ("operator-state.json", "control-state.json"):
            source = session_dir / name
            if not source.is_file():
                continue
            try:
                value = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                states.append("capture_gap")
                continue
            state = value.get("state") if isinstance(value, dict) else None
            states.append(state if isinstance(state, str) else "capture_gap")
        for priority in (
            "capture_gap",
            "quarantined",
            "stopped",
            "paused",
            "draining",
            "running",
        ):
            if priority in states:
                return priority
        return states[0] if states else None

    @staticmethod
    def _operator_available(session: SessionRecord) -> bool:
        if session.state not in {"starting", "running", "draining"}:
            return False
        try:
            value = json.loads(session.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(value, dict):
            return False
        digest = hashlib.sha256(session.session_id.encode()).hexdigest()[:20]
        expected = Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
        return (
            value.get("operator_socket") == str(expected)
            and expected.is_socket()
            and (session.session_dir / "control.token").is_file()
        )
