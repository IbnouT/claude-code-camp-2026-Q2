"""Rules-first parsing of MUD frames into traceable observations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

PARSER_VERSION = "rules-2"
SGR = re.compile(r"\x1b\[([0-9;]*)m")
TITLE_COLOUR = "0;33"
EXITS_COLOUR = "0;36"
OBJECT_COLOUR = "0;32"
DANGER_COLOUR = "0;31"

EXITS_LINE = re.compile(r"^\[?\s*(Obvious exits|Exits):", re.I)
EXITS_NONE = re.compile(r"^\s*None!?\s*$", re.I)
VITALS_LINE = re.compile(r"(\d+)H\s+(\d+)M\s+(\d+)V")
PROMPT_LINE = re.compile(r"^[\d\s]*H[\d\s]*M[\d\s]*V.*>\s*$")
SCORE_VITALS_LINE = re.compile(
    r"You have (\d+)\((\d+)\) hit, (\d+)\((\d+)\) mana "
    r"and (\d+)\((\d+)\) movement points\.",
    re.I,
)
SCORE_ECONOMY_LINE = re.compile(
    r"You have (\d+) exp, (\d+) gold coins, and (\d+) questpoints\.",
    re.I,
)
SCORE_RANK_LINE = re.compile(r"This ranks you as .+ \(level (\d+)\)", re.I)
SCORE_ALIGNMENT_LINE = re.compile(r"your alignment is (-?\d+)", re.I)
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
CONDITION_LINE = re.compile(
    r"^You are (hungry|thirsty|drunk|intoxicated|poisoned|too exhausted)\.?",
    re.I,
)
POISON_LINE = re.compile(r"\b(you are poisoned|poison courses through)\b", re.I)
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
class PlayerStateObservation(Observation):
    """A typed subset of player state observed in one source line."""

    values: dict[str, int | bool | str] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechObservation(Observation):
    who: str = ""
    channel: str = ""
    said: str = ""


@dataclass(frozen=True)
class UnparsedObservation(Observation):
    pass


def segments(raw: bytes | str) -> list[Segment]:
    """The frame as lines, each with the colour it is actually printed in.

    The game closes a colour after the line break, so every line but the
    first opens with the previous line's reset. Reading the first code
    found therefore reports the reset rather than the colour the line is
    written in, and the colour is how this game says whether a thing is a
    creature or an object. What counts is the code in force where the
    text begins.
    """
    text = raw.decode("latin-1") if isinstance(raw, bytes) else raw
    found: list[Segment] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        plain = SGR.sub("", line).strip()
        if not plain:
            continue
        opening = line[:line.index(plain[0])] if plain[0] in line else line
        codes = SGR.findall(opening)
        colour = codes[-1] if codes else None
        if colour in (None, "0", "00"):
            match = SGR.search(line)
            colour = match.group(1) if match else None
        found.append(Segment(plain, colour))
    return found


def normalized_text(raw: bytes | str) -> str:
    """Return the exact plain-text frame consumed by the typed parser."""

    return "\n".join(segment.text for segment in segments(raw))


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
    frame_segments = segments(raw)
    frame_text = "\n".join(segment.text for segment in frame_segments)
    score_conditions = {
        "hungry": bool(re.search(r"\bYou are hungry\.", frame_text, re.I)),
        "thirsty": bool(re.search(r"\bYou are thirsty\.", frame_text, re.I)),
        "drunk": bool(
            re.search(r"\bYou are (?:drunk|intoxicated)\.", frame_text, re.I)
        ),
        "poisoned": bool(POISON_LINE.search(frame_text)),
    }

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

    for segment in frame_segments:
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

        score_vitals = SCORE_VITALS_LINE.search(line)
        if score_vitals:
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "score-vitals",
                PlayerStateObservation,
                values={
                    "hit": int(score_vitals.group(1)),
                    "max_hit": int(score_vitals.group(2)),
                    "mana": int(score_vitals.group(3)),
                    "max_mana": int(score_vitals.group(4)),
                    "move": int(score_vitals.group(5)),
                    "max_move": int(score_vitals.group(6)),
                    **score_conditions,
                },
            )
            continue

        score_economy = SCORE_ECONOMY_LINE.search(line)
        if score_economy:
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "score-economy",
                PlayerStateObservation,
                values={
                    "exp": int(score_economy.group(1)),
                    "gold": int(score_economy.group(2)),
                    "questpoints": int(score_economy.group(3)),
                },
            )
            continue

        score_rank = SCORE_RANK_LINE.search(line)
        if score_rank:
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "score-rank",
                PlayerStateObservation,
                values={"level": int(score_rank.group(1))},
            )
            continue

        score_alignment = SCORE_ALIGNMENT_LINE.search(line)
        if score_alignment:
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "score-alignment",
                PlayerStateObservation,
                values={"alignment": int(score_alignment.group(1))},
            )
            continue

        if EXITS_LINE.match(line):
            exits = _exits_from(line)
            if room is not None:
                room["exits"] = list(exits)
                room["exits_text"] = line
                # The room's own text ends here. Everything after the exits
                # is what happens to be in the room right now: a creature,
                # something on the floor, a line of combat. Letting any of
                # that into the description makes one room read as two on a
                # later visit.
                room["described"] = True
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
                "described": False,
                "exits": [],
                "exits_text": None,
                "mobs": [],
                "objects": [],
                "events": [],
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
            if room["described"]:
                # After the exits, a line that looks like neither a creature
                # nor an object is something that happened, not something
                # present. Filing it as a creature would have the agent
                # remember "You flee head over heels" as an inhabitant.
                room["events"].append(line)
            else:
                room["description"].append(line)
            room["source_lines"] += 1
            continue

        posture = _posture(line)
        if posture is not None:
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "posture-phrase",
                PlayerStateObservation,
                values={"posture": posture},
            )
            continue

        condition = CONDITION_LINE.search(line)
        if condition or POISON_LINE.search(line):
            values: dict[str, int | bool | str] = {}
            if condition:
                name = condition.group(1).casefold()
                if name == "intoxicated":
                    name = "drunk"
                if name in score_conditions:
                    values[name] = True
            if POISON_LINE.search(line):
                values["poisoned"] = True
            add(
                "player_state",
                line,
                Confidence.HIGH,
                "condition-phrase",
                PlayerStateObservation,
                values=values,
            )
            continue

        classified = (
            ("death", DEATH_LINE, "death-phrase"),
            ("dark", DARK_LINE, "darkness-phrase"),
            ("door", DOOR_LINE, "door-phrase"),
            ("refused", REFUSED_LINE, "refusal-phrase"),
            ("advisory", ADVISORY_LINE, "advisory-phrase"),
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


def _posture(line: str) -> str | None:
    direct = re.search(
        r"^You are (standing|sitting|resting|sleeping|fighting|incapacitated)\.",
        line,
        re.I,
    )
    if direct:
        return direct.group(1).casefold()
    transitions = (
        (r"^You sit down", "sitting"),
        (r"^You (stand up|stop resting|awaken|wake)", "standing"),
        (r"^You rest", "resting"),
        (r"^You go to sleep", "sleeping"),
    )
    for pattern, posture in transitions:
        if re.search(pattern, line, re.I):
            return posture
    return None


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
