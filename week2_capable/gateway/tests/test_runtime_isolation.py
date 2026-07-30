"""Gateway binding to launcher-owned identity and journal paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from mud_gateway.journal import Journal, JournalError
from mud_gateway.settings import GatewaySettings


def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / ".boukensha"
    config.mkdir()
    (config / "settings.yaml").write_text(
        """
gateway:
  connection:
    player_profile: alpha
  players:
    alpha:
      character: Alpha
      password_env: PLAYER_ALPHA
    beta:
      character: Beta
      password_env: PLAYER_BETA
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOUKENSHA_DIR", str(config))
    return config


def test_runtime_identity_selects_exact_profile_and_session_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(tmp_path, monkeypatch)
    session_dir = tmp_path / "profiles" / "beta" / "sessions" / "session-id"
    session_dir.mkdir(parents=True)
    monkeypatch.setenv("BOUKENSHA_PLAYER_ID", "beta")
    monkeypatch.setenv("BOUKENSHA_AGENT_ID", "agent-id")
    monkeypatch.setenv("BOUKENSHA_SESSION_ID", "session-id")
    monkeypatch.setenv("BOUKENSHA_GATEWAY_SESSION_ID", "gateway-id")
    monkeypatch.setenv("BOUKENSHA_SESSION_DIR", str(session_dir))
    monkeypatch.setenv("PLAYER_BETA", "beta-secret")
    (tmp_path / ".boukensha" / ".env").write_text(
        "MUD_ADMIN_PASSWORD=admin-secret\n",
        encoding="utf-8",
    )

    settings = GatewaySettings.load()

    assert settings.player_profile == "beta"
    assert settings.character == "Beta"
    assert settings.password == "beta-secret"
    assert settings.journal == session_dir / "gateway.db"
    assert settings.agent_id == "agent-id"
    assert settings.session_id == "session-id"
    assert settings.gateway_session_id == "gateway-id"
    assert settings.admin_password is None


def test_runtime_journal_is_create_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "gateway.db"
    journal = Journal(path, exclusive=True)
    with pytest.raises(JournalError, match="already has a writer"):
        Journal(path, exclusive=True)
    journal.close()

    reopened = Journal(path, exclusive=True)
    reopened.close()


def test_corrupt_journal_is_preserved_as_a_capture_gap(tmp_path: Path) -> None:
    path = tmp_path / "gateway.db"
    path.write_bytes(b"not sqlite")

    with pytest.raises(JournalError, match="integrity failure"):
        Journal(path)

    assert not path.exists()
    preserved = list(tmp_path.glob("gateway.db.corrupt-*"))
    assert len(preserved) == 1
    assert preserved[0].read_bytes() == b"not sqlite"
