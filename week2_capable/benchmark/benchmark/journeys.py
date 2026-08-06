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
    title: str | None = None
    clue: str | None = None

    @property
    def objective_title(self) -> str:
        """Return the concise authored title retained for observers."""
        return self.title or self.order


@dataclass(frozen=True)
class Verdict:
    """Whether journal evidence proves the journey objective."""

    success: bool
    evidence: tuple[str, ...]


J1 = Journey(
    "J1",
    "Find the bakery and read the menu.",
    title="Find the bakery and read the menu",
)
J2 = Journey(
    "J2",
    "Travel north from the Temple into the newbie zone and find the Massive Minotaur.",
    title="Find the Massive Minotaur",
    clue="north of the Temple · newbie area",
)
J3 = Journey(
    "J3",
    "Find the minotaur and kill it.",
    title="Kill the Massive Minotaur",
)
JOURNEYS = {journey.id: journey for journey in (J1, J2, J3)}

_MENU_ROW = re.compile(r"^\s*\d+\)\s+.*(?:bread|danish|cake|pastry)", re.IGNORECASE)
_BAKERY_GOOD = re.compile(r"\b(?:bread|danish|cake|pastry)\b", re.IGNORECASE)
_MINOTAUR = re.compile(r"\bmassive minotaur\b", re.IGNORECASE)
_MINOTAUR_DEAD = re.compile(
    r"massive minotaur is dead|massive minotaur'?s death cry",
    re.IGNORECASE,
)


def judge(journey: Journey, events: Iterable[Mapping[str, object]]) -> Verdict:
    """Judge a journey from gateway evidence, never from the model's claim."""
    material = list(events)
    if journey.id == "J2":
        evidence: list[str] = []
        for event in material:
            if event.get("kind") != "observation":
                continue
            payload = event.get("payload")
            text = flatten_payload(payload if isinstance(payload, dict) else {})
            evidence.extend(
                line.strip()
                for line in text.splitlines()
                if _MINOTAUR.search(line)
            )
        unique = tuple(dict.fromkeys(evidence))
        return Verdict(bool(unique), unique[:8])
    if journey.id == "J3":
        kills: list[str] = []
        sightings: list[str] = []
        for event in material:
            if event.get("kind") != "observation":
                continue
            payload = event.get("payload")
            text = flatten_payload(payload if isinstance(payload, dict) else {})
            for line in text.splitlines():
                if _MINOTAUR_DEAD.search(line):
                    kills.append(line.strip())
                elif _MINOTAUR.search(line):
                    sightings.append(line.strip())
        evidence = tuple(dict.fromkeys([*kills, *sightings]))
        return Verdict(bool(kills), evidence[:8])
    if journey.id != "J1":
        raise ValueError(f"unknown journey {journey.id!r}")
    rows: list[str] = []
    goods: list[str] = []
    bakery_seen = False
    for event in material:
        payload = event.get("payload")
        text = flatten_payload(payload if isinstance(payload, dict) else event)
        if "the bakery" in text.lower():
            bakery_seen = True
        for line in text.splitlines():
            if _MENU_ROW.search(line):
                rows.append(line.strip())
            if bakery_seen and _BAKERY_GOOD.search(line):
                goods.append(line.strip())
    evidence = tuple(dict.fromkeys([*rows, *goods]))
    return Verdict(bool(bakery_seen and rows and goods), evidence[:8])


def flatten_payload(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_payload(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(flatten_payload(item) for item in value)
    return ""
