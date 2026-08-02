"""Canonical retained-source identity validation."""

from __future__ import annotations

from pathlib import Path

from .errors import PathIdentityError


def validate_session_directory(
    config_dir: Path,
    *,
    player_id: str,
    session_id: str,
    session_dir: Path,
    manifest_path: Path,
) -> Path:
    """Return the canonical session directory or reject path substitution."""
    _validate_segment(player_id, label="player_id")
    _validate_segment(session_id, label="session_id")
    expected = (config_dir / "profiles" / player_id / "sessions" / session_id).resolve(
        strict=False
    )
    actual = session_dir.expanduser().resolve(strict=False)
    if actual != expected:
        raise PathIdentityError(
            session_dir,
            "directory does not match registry player and session identity",
        )
    expected_manifest = expected / "session.json"
    actual_manifest = manifest_path.expanduser().resolve(strict=False)
    if actual_manifest != expected_manifest:
        raise PathIdentityError(
            manifest_path,
            "manifest does not belong to the declared session directory",
        )
    return expected


def _validate_segment(value: str, *, label: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise PathIdentityError(Path(value), f"invalid {label}")
