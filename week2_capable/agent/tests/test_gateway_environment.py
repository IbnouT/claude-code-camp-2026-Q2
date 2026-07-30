"""The gateway child receives only its selected mortal identity."""

from __future__ import annotations

from pathlib import Path

import pytest

from boukensha.config import Config


def test_gateway_mcp_environment_excludes_provider_admin_and_other_player(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
mcp_servers:
  mud:
    command: boukensha-gateway
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOUKENSHA_DIR", str(config))
    monkeypatch.setenv("BOUKENSHA_PLAYER_ID", "alpha")
    monkeypatch.setenv("BOUKENSHA_SESSION_ID", "session-id")
    monkeypatch.setenv("BOUKENSHA_GATEWAY_SESSION_ID", "gateway-id")
    monkeypatch.setenv("BOUKENSHA_ADMIN_SECRET_FILE", "/private/admin.env")
    monkeypatch.setenv("BOUKENSHA_LAUNCH_TASK", "private benchmark objective")
    monkeypatch.setenv("BOUKENSHA_RESET_BASELINE", "level1-temple@1")
    monkeypatch.setenv("PLAYER_ALPHA", "alpha-secret")
    monkeypatch.setenv("PLAYER_BETA", "beta-secret")
    monkeypatch.setenv("MUD_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-secret")

    entry = Config().mcp_servers()["mud"]

    assert entry["inherit_env"] is False
    assert entry["env"]["PLAYER_ALPHA"] == "alpha-secret"
    assert entry["env"]["BOUKENSHA_SESSION_ID"] == "session-id"
    assert entry["env"]["BOUKENSHA_GATEWAY_SESSION_ID"] == "gateway-id"
    assert entry["env"]["BOUKENSHA_ADMIN_SECRET_FILE"] == "/private/admin.env"
    assert "BOUKENSHA_LAUNCH_TASK" not in entry["env"]
    assert "BOUKENSHA_RESET_BASELINE" not in entry["env"]
    assert "PLAYER_BETA" not in entry["env"]
    assert "MUD_ADMIN_PASSWORD" not in entry["env"]
    assert "ANTHROPIC_API_KEY" not in entry["env"]
