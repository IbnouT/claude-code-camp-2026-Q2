"""Rules-first parsing of MUD frames into traceable observations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

PARSER_VERSION = "rules-1"
SGR = re.compile(r"\x1b\[([0-9;]*)m")
TITLE_COLOUR = "0;33"
EXITS_COLOUR = "0;36"
OBJECT_COLOUR = "0;32"
DANGER_COLOUR = "0;31"

EXITS_LINE = re.compile(r"^\[?\s*(Obvious exits|Exits):", re.I)
EXITS_NONE = re.compile(r"^\s*None!?\s*$", re.I)
VITALS_LINE = re.compile(r"(\d+)H\s+(\d+)M\s+(\d+)V")
PROMPT_LINE = re.compile(r"^[\d\s]*H[\d\s]*M[\d\s]*V.*>\s*$")
OBJECT_HERE = re.compile(r"(lies here|is lying here|has been left here)\.?$", re.I)
MOB_HERE = re.compile(
    r"(is here|stands here|is standing here|is sitting here|is resting here|"
    r"is sleeping here|rests here|sleeps here)",
    re.I,
)
CREATURE_ACTING = re.compile(r"^(a|an|the)\b.{0,60}?\b(is|are)\s+\w+ing\b", re.I)
SECOND_PERSON = re.compile(r"^You\b", re.I)
REFUSED_LINE = re.compile(
    r"you cannot go that way|alas, you cannot go|you can't|blocks your way|"
    r"should get on your feet|seems to be closed",
    re.I,
)
ADVISORY_LINE = re.compile(
    r"this zone is above your recommended level|better be careful", re.I
)
DARK_LINE = re.compile(r"it is pitch black|you can't see a thing", re.I)
DEATH_LINE = re.compile(r"you are dead|you have been killed|R\.I\.P", re.I)
DOOR_LINE = re.compile(
    r"seems to be closed|is closed\.|is now closed|is locked|"
    r"you (open|close|unlock|lock) the",
    re.I,
)
COMBAT_LINE = re.compile(
    r"\b(hits?|misses|slash(es)?|pierce[sd]?|crush(es)?|bites?|claws?|"
    r"attacks?|parr(y|ies)|dodge[sd]?|punch(es)?|kicks?)\b",
    re.I,
)
SPEECH_LINE = re.compile(
    r"^(\w+) (says|shouts|gossips|tells you|yells|whispers),?\s*'(.*)'", re.I
)
POSTURE_LINE = re.compile(
    r"^You (sit down|stop resting|stand up|go to sleep|awaken|rest|wake)|"
    r"^You are (standing|sitting|resting|sleeping)\.",
    re.I,
)
CONDITION_LINE = re.compile(r"^You are (hungry|thirsty|drunk|too exhausted)\.?", re.I)
ITEM_LINE = re.compile(r"^You (get|drop|put|wear|wield|remove|eat|drink) ", re.I)
FURNITURE_LINE = re.compile(
    r"^[-=~_]{3,}\s*$|^\s*##\s+Available\s+Item\s+Cost|"
    r"^(You are carrying|You are using|Your inventory)",
    re.I,
)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class WireReference:
    """The durable source range behind an observation."""

    source: str
    first_seq: int
    last_seq: int
    digest: str

    @classmethod
    def from_bytes(
        cls, source: str, first_seq: int, last_seq: int, raw: bytes | str
    ) -> "WireReference":
        body = raw.encode("latin-1") if isinstance(raw, str) else raw
        return cls(
            source=source,
            first_seq=first_seq,
            last_seq=last_seq,
            digest=hashlib.sha256(body).hexdigest()[:32],
        )


@dataclass(frozen=True)
class Segment:
    text: str
    sgr: str | None


@dataclass(frozen=True)
class Observation:
    kind: str
    text: str
    confidence: Confidence
    method: str
    wire_ref: WireReference
    parser_version: str = PARSER_VERSION
    source_lines: int = 1

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["confidence"] = self.confidence.value
        value["wire_ref"] = asdict(self.wire_ref)
        return value


@dataclass(frozen=True)
class RoomObservation(Observation):
    title: str = ""
    description: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()
    mobs: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExitsObservation(Observation):
    exits: tuple[str, ...] = ()


@dataclass(frozen=True)
class VitalsObservation(Observation):
    hit: int = 0
    mana: int = 0
    move: int = 0


@dataclass(frozen=True)
class StateObservation(Observation):
    state: str = ""


@dataclass(frozen=True)
class SpeechObservation(Observation):
    who: str = ""
    channel: str = ""
    said: str = ""


@dataclass(frozen=True)
class UnparsedObservation(Observation):
    pass


def segments(raw: bytes | str) -> list[Segment]:
    text = raw.decode("latin-1") if isinstance(raw, bytes) else raw
    found: list[Segment] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        match = SGR.search(line)
        plain = SGR.sub("", line).strip()
        if plain:
            found.append(Segment(plain, match.group(1) if match else None))
    return found


def _is_title(line: str) -> bool:
    if MOB_HERE.search(line) or SECOND_PERSON.match(line):
        return False
    return not CREATURE_ACTING.match(line)


def _exits_from(line: str) -> tuple[str, ...]:
    body = re.sub(r"^\[?\s*(Obvious exits|Exits):", "", line, flags=re.I)
    body = body.strip().rstrip("]").strip()
    if not body or EXITS_NONE.match(body):
        return ()
    if "-" in body:
        return tuple(
            part.split("-")[0].strip().lower()
            for part in body.split("\n")
            if part.strip()
        )
    return tuple(token.strip("()").lower() for token in body.split() if token.strip("()"))


def parse(raw: bytes | str, wire_ref: WireReference) -> list[Observation]:
    """Parse all nonblank lines, retaining anything unknown."""

    found: list[Observation] = []
    room: dict[str, Any] | None = None

    def add(
        kind: str,
        text: str,
        confidence: Confidence,
        method: str,
        cls: type[Observation] = Observation,
        **values: Any,
    ) -> None:
        found.append(
            cls(
                kind=kind,
                text=text,
                confidence=confidence,
                method=method,
                wire_ref=wire_ref,
                **values,
            )
        )

    def close_room() -> None:
        nonlocal room
        if room is None:
            return
        found.append(
            RoomObservation(
                kind="room",
                text=room["title"],
                confidence=Confidence.HIGH,
                method="ansi-title+room-frame",
                wire_ref=wire_ref,
                source_lines=room["source_lines"],
                title=room["title"],
                description=tuple(room["description"]),
                exits=tuple(room["exits"]),
                mobs=tuple(room["mobs"]),
                objects=tuple(room["objects"]),
            )
        )
        if room["exits_text"] is not None:
            found.append(
                ExitsObservation(
                    kind="exits",
                    text=room["exits_text"],
                    confidence=Confidence.HIGH,
                    method="exits-shape+ansi",
                    wire_ref=wire_ref,
                    exits=tuple(room["exits"]),
                )
            )
        room = None

    for segment in segments(raw):
        line, sgr = segment.text, segment.sgr

        if PROMPT_LINE.match(line):
            close_room()
            vitals = VITALS_LINE.search(line)
            if vitals:
                add(
                    "vitals",
                    line,
                    Confidence.HIGH,
                    "prompt-shape",
                    VitalsObservation,
                    hit=int(vitals.group(1)),
                    mana=int(vitals.group(2)),
                    move=int(vitals.group(3)),
                )
            continue

        if EXITS_LINE.match(line):
            exits = _exits_from(line)
            if room is not None:
                room["exits"] = list(exits)
                room["exits_text"] = line
            else:
                add(
                    "exits",
                    line,
                    Confidence.HIGH,
                    "exits-shape+ansi",
                    ExitsObservation,
                    exits=exits,
                )
            continue

        if sgr == TITLE_COLOUR and room is not None:
            room["mobs"].append(line)
            room["source_lines"] += 1
            continue

        if sgr == TITLE_COLOUR and _is_title(line):
            close_room()
            room = {
                "title": line,
                "description": [],
                "exits": [],
                "exits_text": None,
                "mobs": [],
                "objects": [],
                "source_lines": 1,
            }
            continue

        if room is not None:
            if sgr == OBJECT_COLOUR or OBJECT_HERE.search(line):
                room["objects"].append(line)
                room["source_lines"] += 1
                continue
            if MOB_HERE.search(line) or CREATURE_ACTING.match(line):
                room["mobs"].append(line)
                room["source_lines"] += 1
                continue
            room["description"].append(line)
            room["source_lines"] += 1
            continue

        classified = (
            ("death", DEATH_LINE, "death-phrase"),
            ("dark", DARK_LINE, "darkness-phrase"),
            ("door", DOOR_LINE, "door-phrase"),
            ("refused", REFUSED_LINE, "refusal-phrase"),
            ("advisory", ADVISORY_LINE, "advisory-phrase"),
            ("posture", POSTURE_LINE, "posture-phrase"),
            ("condition", CONDITION_LINE, "condition-phrase"),
            ("item", ITEM_LINE, "item-verb"),
        )
        matched = False
        for kind, pattern, method in classified:
            if pattern.search(line):
                add(kind, line, Confidence.HIGH, method, StateObservation, state=kind)
                matched = True
                break
        if matched:
            continue

        speech = SPEECH_LINE.match(line)
        if speech:
            add(
                "speech",
                line,
                Confidence.HIGH,
                "speech-shape",
                SpeechObservation,
                who=speech.group(1),
                channel=speech.group(2).lower(),
                said=speech.group(3),
            )
            continue

        if FURNITURE_LINE.match(line):
            add("furniture", line, Confidence.HIGH, "structure-shape")
            continue

        if sgr == DANGER_COLOUR or COMBAT_LINE.search(line):
            add("combat", line, Confidence.MEDIUM, "combat-colour-or-verb")
            continue

        add(
            "unparsed",
            line,
            Confidence.LOW,
            f"unmatched-colour:{sgr or 'none'}",
            UnparsedObservation,
        )

    close_room()
    return found


@dataclass
class Coverage:
    lines: int = 0
    typed: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    unparsed_samples: list[str] = field(default_factory=list)

    @property
    def miss_rate(self) -> float:
        return 0.0 if not self.lines else (self.lines - self.typed) / self.lines

    def add(self, observations: list[Observation]) -> None:
        for observation in observations:
            self.lines += observation.source_lines
            self.by_kind[observation.kind] = self.by_kind.get(observation.kind, 0) + 1
            if isinstance(observation, UnparsedObservation):
                if len(self.unparsed_samples) < 40:
                    self.unparsed_samples.append(observation.text[:120])
            else:
                self.typed += observation.source_lines

