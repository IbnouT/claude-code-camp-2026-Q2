"""The standing advice a player carries into a game they know how to play.

These are not instructions the harness executes. They are what a person
who has played this kind of game would keep in mind, written down so the
agent carries them too, and written as configuration so any one of them
can be switched off and its worth measured.

The model reads them and decides. Nothing here acts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


@dataclass(frozen=True)
class Rule:
    """One piece of standing advice, with the numbers it depends on."""

    id: str
    text: str
    enabled: bool = True
    settings: Mapping[str, Any] | None = None

    def render(self, values: Mapping[str, Any]) -> str:
        """The advice with its numbers filled in from settings."""
        try:
            return self.text.format(**values)
        except (KeyError, IndexError):
            return self.text


def load(path: Path) -> tuple[Rule, ...]:
    """Read the authored rules. A missing file means no advice, not a fault."""
    if not path.is_file():
        return ()
    document = yaml.safe_load(path.read_text()) or {}
    entries = document.get("rules") or []
    rules = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        identity = str(entry.get("id") or "").strip()
        text = str(entry.get("text") or "").strip()
        if not identity or not text:
            continue
        rules.append(
            Rule(
                id=identity,
                text=text,
                enabled=bool(entry.get("enabled", True)),
                settings=entry.get("settings"),
            )
        )
    return tuple(rules)


def render(rules: Sequence[Rule], values: Mapping[str, Any]) -> str:
    """The enabled rules as one short block, or nothing when all are off."""
    lines = [
        f"- {rule.render(values)}" for rule in rules if rule.enabled
    ]
    if not lines:
        return ""
    return "how to play:\n" + "\n".join(lines)


def by_id(rules: Sequence[Rule]) -> dict[str, Rule]:
    """The rules keyed by id, so a decision can cite the one it followed."""
    return {rule.id: rule for rule in rules}
