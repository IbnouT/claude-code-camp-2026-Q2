"""Configured public player identities from the gateway settings.

The launcher must be able to offer Start to a configured player that has never
run a session. Those identities live in the gateway settings, not in the session
registry. Only the public ``id`` and ``character`` are exposed here. Secrets
(``password_env`` and any resolved password) are never surfaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mud_gateway.settings import GatewaySettings, GatewaySettingsError


@dataclass(frozen=True, slots=True)
class ConfiguredPlayer:
    """One public configured identity, with no secret material."""

    id: str
    character: str


def configured_players(runtime_root: Path) -> tuple[ConfiguredPlayer, ...]:
    """Return the public configured identities for the served runtime root.

    A missing or invalid gateway configuration yields no configured identities
    rather than a failure, so the catalog degrades to session-derived players.
    """
    try:
        settings = GatewaySettings.load(config_dir=runtime_root)
    except (GatewaySettingsError, OSError):
        return ()
    return tuple(
        ConfiguredPlayer(id=profile.id, character=profile.character)
        for profile in settings.players.values()
    )
