"""Journey orders and evidence-based success predicates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class Journey:
    """One repeatable game objective."""

    id: str
    order: str


@dataclass(frozen=True)
class Verdict:
    """Whether journal evidence proves the journey objective."""

    success: bool
    evidence: tuple[str, ...]


J1 = Journey("J1", "Find the bakery and read the menu.")

_MENU_ROW = re.compile(r"^\s*\d+\)\s+.*(?:bread|danish|cake|pastry)", re.IGNORECASE)
_BAKERY_GOOD = re.compile(r"\b(?:bread|danish|cake|pastry)\b", re.IGNORECASE)


def judge(journey: Journey, events: Iterable[Mapping[str, object]]) -> Verdict:
    """Judge a journey from gateway evidence, never from the model's claim."""
    if journey.id != "J1":
        raise ValueError(f"unknown journey {journey.id!r}")
    rows: list[str] = []
    goods: list[str] = []
    bakery_seen = False
    for event in events:
        payload = event.get("payload")
        text = _flatten(payload if isinstance(payload, dict) else event)
        if "the bakery" in text.lower():
            bakery_seen = True
        for line in text.splitlines():
            if _MENU_ROW.search(line):
                rows.append(line.strip())
            if bakery_seen and _BAKERY_GOOD.search(line):
                goods.append(line.strip())
    evidence = tuple(dict.fromkeys([*rows, *goods]))
    return Verdict(bool(bakery_seen and rows and goods), evidence[:8])


def _flatten(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_flatten(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten(item) for item in value)
    return ""
