from __future__ import annotations

from pathlib import Path

import pytest

from mud_gateway.settings import GatewaySettings, GatewaySettingsError


def _configure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> Path:
    directory = tmp_path / ".boukensha"
    directory.mkdir()
    (directory / "settings.yaml").write_text(text, encoding="utf-8")
    (directory / ".env").write_text(
        "MUD_PASSWORD=player-secret\nMUD_ADMIN_PASSWORD=admin-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOUKENSHA_DIR", str(directory))
    monkeypatch.delenv("MUD_PASSWORD", raising=False)
    monkeypatch.delenv("MUD_ADMIN_PASSWORD", raising=False)
    return directory


def test_gateway_loads_yaml_and_secrets_from_the_shared_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _configure(
        tmp_path,
        monkeypatch,
        """
gateway:
  connection:
    host: mud.example
    port: 4444
    player_profile: hero
  players:
    hero:
      character: HeroName
      password_env: HERO_PASSWORD
  journal: evidence/gateway.db
  surface:
    profile: direct-core
    enable: [cast_spell]
    disable: [tell]
    allow_raw: true
  api:
    host: 0.0.0.0
    port: 9000
  admin:
    character: builder
    password_env: MUD_ADMIN_PASSWORD
  reset:
    pause_timeout_seconds: 7
    child_timeout_seconds: 11
    client_timeout_seconds: 19
""",
    )
    monkeypatch.setenv("HERO_PASSWORD", "hero-secret")

    settings = GatewaySettings.load()

    assert settings.host == "mud.example"
    assert settings.port == 4444
    assert settings.player_profile == "hero"
    assert settings.character == "HeroName"
    assert settings.journal == tmp_path / "evidence" / "gateway.db"
    assert settings.password == "hero-secret"
    assert settings.admin_password == "admin-secret"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000
    assert settings.admin_character == "builder"
    assert settings.reset_pause_timeout == 7
    assert settings.reset_child_timeout == 11
    assert settings.reset_client_timeout == 19
    assert "cast_spell" in settings.effective_profile().allowed
    assert "send_raw" in settings.effective_profile().allowed
    assert "tell" not in settings.effective_profile().allowed
    assert settings.config_dir == directory


def test_profile_secret_file_isolated_from_admin_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _configure(
        tmp_path,
        monkeypatch,
        """
gateway:
  connection:
    player_profile: scout
  players:
    scout:
      character: Scout
      password_env: SCOUT_PASSWORD
  admin:
    character: builder
    password_env: BUILDER_PASSWORD
""",
    )
    profile_dir = directory / "profiles" / "scout"
    profile_dir.mkdir(parents=True)
    (profile_dir / ".env").write_text(
        "SCOUT_PASSWORD=scout-secret\n",
        encoding="utf-8",
    )
    (directory / ".env").write_text(
        "BUILDER_PASSWORD=builder-secret\n",
        encoding="utf-8",
    )

    settings = GatewaySettings.load()

    assert settings.player_password("scout") == "scout-secret"
    assert settings.admin_password == "builder-secret"
    assert settings.player_password_envs == {"SCOUT_PASSWORD"}


def test_raw_capability_has_one_explicit_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        tmp_path,
        monkeypatch,
        "gateway:\n  surface:\n    enable: [send_raw]\n",
    )

    with pytest.raises(GatewaySettingsError, match="allow_raw"):
        GatewaySettings.load()


def test_unknown_gateway_setting_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(tmp_path, monkeypatch, "gateway:\n  surprise: true\n")

    with pytest.raises(GatewaySettingsError, match="surprise"):
        GatewaySettings.load()


def test_admin_and_player_secret_names_must_differ(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        tmp_path,
        monkeypatch,
        """
gateway:
  players:
    default:
      character: hero
      password_env: SAME_PASSWORD
  admin:
    character: builder
    password_env: SAME_PASSWORD
""",
    )

    with pytest.raises(GatewaySettingsError, match="must differ"):
        GatewaySettings.load()


def test_reset_timeouts_must_be_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        tmp_path,
        monkeypatch,
        "gateway:\n  reset:\n    child_timeout_seconds: 0\n",
    )

    with pytest.raises(GatewaySettingsError, match="must be positive"):
        GatewaySettings.load()


def test_capabilities_default_off_and_load_from_their_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _configure(tmp_path, monkeypatch, "gateway:\n  connection: {}\n")
    absent = GatewaySettings.load()
    assert absent.capabilities == {
        "knowledge": False,
        "navigation": False,
        "survival": False,
        "economy": False,
        "campaign": False,
    }

    (directory / "settings.yaml").write_text(
        """
gateway:
  connection: {}
capabilities:
  navigation:
    enabled: true
    sweep_max_rooms: 40
  survival:
    enabled: false
""",
        encoding="utf-8",
    )
    loaded = GatewaySettings.load()
    assert loaded.capabilities["navigation"] is True
    assert loaded.capabilities["survival"] is False
    assert loaded.capabilities["campaign"] is False
    assert loaded.capability_settings["navigation"]["sweep_max_rooms"] == 40


def test_unknown_capability_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        tmp_path,
        monkeypatch,
        "gateway:\n  connection: {}\ncapabilities:\n  telepathy:\n    enabled: true\n",
    )
    with pytest.raises(GatewaySettingsError):
        GatewaySettings.load()


def test_a_launched_session_reads_the_secret_file_it_was_given(tmp_path, monkeypatch):
    """The launcher hands a child the file to read. Without this the
    immortal connection has no credential and never opens."""
    from mud_gateway.settings import GatewaySettings

    secrets = tmp_path / "admin.env"
    secrets.write_text("MUD_ADMIN_PASSWORD=from-the-file\n", encoding="utf-8")
    monkeypatch.delenv("MUD_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("BOUKENSHA_ADMIN_SECRET_FILE", str(secrets))
    settings = GatewaySettings(config_dir=tmp_path, session_id="a-session")

    assert settings.admin_password == "from-the-file"


def test_a_launched_session_reads_no_file_it_was_not_given(tmp_path, monkeypatch):
    """Falling back to the configuration directory would let a child read
    a secret the launcher chose not to hand it."""
    from mud_gateway.settings import GatewaySettings

    (tmp_path / ".env").write_text(
        "MUD_ADMIN_PASSWORD=not-for-you\n", encoding="utf-8"
    )
    monkeypatch.delenv("MUD_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("BOUKENSHA_ADMIN_SECRET_FILE", raising=False)
    settings = GatewaySettings(config_dir=tmp_path, session_id="a-session")

    assert settings.admin_password is None
