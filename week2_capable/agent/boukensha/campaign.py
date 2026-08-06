"""Deterministic campaign phases over typed mission readiness.

The controller decides WHICH phase the mission is in from numbers and
typed facts; the model decides only what to do inside that phase. The
decision rides the volatile state message every call, so the mission
spine never leaves the model's view and never accumulates in history.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

PHASES = ("survive", "locate", "prepare", "engage")


class CampaignController:
    """Phase selection bound to one mission target."""

    def __init__(
        self,
        fetch_readiness: Callable[[], str | None],
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        block = dict(settings or {})
        self._fetch = fetch_readiness
        self.target = str(block.get("target", "")).strip()
        self.survive_health = float(block.get("survive_health", 0.35))
        self.engage_health = float(block.get("engage_health", 0.8))

    def phase(self, readiness: Mapping[str, Any]) -> tuple[str, str]:
        """The active phase and its reason, from typed readiness only."""
        health = _fraction(readiness.get("hit"), readiness.get("max_hit"))
        if health is not None and health < self.survive_health:
            return "survive", (
                f"health at {int(health * 100)}%: recover before anything"
            )
        if not readiness.get("sighted_places"):
            frontier = readiness.get("frontier_remaining")
            return "locate", (
                f"target not yet sighted, {frontier} rooms hold unexplored "
                "exits: sweep them"
            )
        if health is not None and health < self.engage_health:
            return "prepare", (
                f"target sighted but health at {int(health * 100)}%: "
                "recover and equip before engaging"
            )
        titles = readiness.get("sighted_titles") or []
        where = f" at {titles[0]}" if titles else ""
        return "engage", (
            f"target sighted{where}: travel there, consider it first, "
            "then fight"
        )

    def line(self) -> str | None:
        """The campaign line for the volatile message, or None."""
        if not self.target:
            return None
        raw = self._fetch()
        if not raw:
            return None
        try:
            readiness = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(readiness, dict):
            return None
        phase, reason = self.phase(readiness)
        return f"campaign: {phase} · {reason}"


def _fraction(current: Any, maximum: Any) -> float | None:
    if not isinstance(current, int) or not isinstance(maximum, int):
        return None
    if maximum <= 0:
        return None
    return current / maximum
