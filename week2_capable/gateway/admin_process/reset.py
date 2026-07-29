"""Repeatable benchmark reset, verified through the mortal connection."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from mud_gateway.admin import FED, TEMPLE, AdminSession
from mud_gateway.session import Session

DEFAULT_FIELDS: dict[str, int] = {
    "level": 1,
    "exp": 0,
    "gold": 0,
    "bank": 0,
    "align": 0,
    "hunger": FED,
    "thirst": FED,
    "drunk": 0,
}
SCORE_PATTERNS = {
    "hit": re.compile(r"You have (\d+)\((\d+)\) hit"),
    "mana": re.compile(r"(\d+)\((\d+)\) mana"),
    "move": re.compile(r"(\d+)\((\d+)\) movement"),
    "exp": re.compile(r"You have (\d+) exp,"),
    "gold": re.compile(r"(\d+) gold coins"),
    "level": re.compile(r"\(level (\d+)\)"),
    "align": re.compile(r"alignment is (-?\d+)"),
}
POSITION = re.compile(r"You are (standing|sitting|resting|sleeping)\.")
HUNGRY = re.compile(r"You are hungry\.")
THIRSTY = re.compile(r"You are thirsty\.")


@dataclass(frozen=True)
class ObservedState:
    level: int | None = None
    hit: tuple[int, int] | None = None
    mana: tuple[int, int] | None = None
    move: tuple[int, int] | None = None
    gold: int | None = None
    exp: int | None = None
    align: int | None = None
    position: str | None = None
    hungry: bool | None = None
    thirsty: bool | None = None
    room_title: str | None = None
    exits: tuple[str, ...] | None = None

    @property
    def unread(self) -> list[str]:
        return [
            name
            for name in self.__dataclass_fields__
            if getattr(self, name) is None
        ]

    def differences(self, other: "ObservedState") -> dict[str, tuple[object, object]]:
        return {
            name: (getattr(self, name), getattr(other, name))
            for name in self.__dataclass_fields__
            if getattr(self, name) != getattr(other, name)
        }


@dataclass(frozen=True)
class ResetOutcome:
    reset_id: str
    player: str
    state: ObservedState
    drift: dict[str, tuple[object, object]]
    applied: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.drift and not self.state.unread


def parse_score(text: str) -> dict[str, object]:
    found: dict[str, object] = {}
    for name, pattern in SCORE_PATTERNS.items():
        match = pattern.search(text)
        if match:
            found[name] = (
                (int(match.group(1)), int(match.group(2)))
                if name in {"hit", "mana", "move"}
                else int(match.group(1))
            )
    posture = POSITION.search(text)
    if posture:
        found["position"] = posture.group(1)
    found["hungry"] = bool(HUNGRY.search(text))
    found["thirsty"] = bool(THIRSTY.search(text))
    return found


async def observe_mortal(player: Session) -> ObservedState:
    score = await player.command("score")
    look = await player.command("look")
    facts = parse_score(score.text)
    snapshot = player.observations.snapshot()
    if snapshot.room is not None:
        facts["room_title"] = snapshot.room.title
        facts["exits"] = snapshot.room.exits
    return ObservedState(**facts)


class ResetPlan:
    def __init__(
        self,
        fields: dict[str, int] | None = None,
        *,
        room: int = TEMPLE,
    ) -> None:
        self.fields = dict(DEFAULT_FIELDS if fields is None else fields)
        self.room = room

    async def apply(
        self, admin: AdminSession, player: Session, player_name: str
    ) -> ResetOutcome:
        reset_id = uuid.uuid4().hex
        journal = admin.journal
        journal.append(
            admin.session.id,
            "reset_started",
            {"reset_id": reset_id, "player": player_name, "room": self.room},
        )
        applied: list[str] = []
        await admin.goto(self.room)
        applied.append("goto")
        await admin.transfer(player_name)
        applied.append("transfer")
        await admin.restore(player_name)
        applied.append("restore")
        for name, value in self.fields.items():
            await admin.set_field(player_name, name, value)
            applied.append(name)

        state = await observe_mortal(player)
        drift = self.verify(state)
        journal.append(
            admin.session.id,
            "reset_verified",
            {
                "reset_id": reset_id,
                "player": player_name,
                "ok": not drift and not state.unread,
                "unread": state.unread,
                "drift": drift,
                "applied": applied,
            },
        )
        return ResetOutcome(reset_id, player_name, state, drift, tuple(applied))

    def verify(self, state: ObservedState) -> dict[str, tuple[object, object]]:
        expected: dict[str, object] = {
            "level": self.fields.get("level"),
            "gold": self.fields.get("gold"),
            "exp": self.fields.get("exp"),
            "align": self.fields.get("align"),
            "hungry": not bool(self.fields.get("hunger", 0)),
            "thirsty": not bool(self.fields.get("thirst", 0)),
        }
        drift = {
            name: (wanted, getattr(state, name))
            for name, wanted in expected.items()
            if wanted is not None and getattr(state, name) != wanted
        }
        for name in ("hit", "mana", "move"):
            pair = getattr(state, name)
            if pair is not None and pair[0] != pair[1]:
                drift[name] = ("full", pair)
        return drift
