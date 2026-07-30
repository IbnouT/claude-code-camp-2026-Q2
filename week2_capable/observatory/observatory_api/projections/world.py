"""Build an uncertainty-preserving world graph from gateway evidence."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mud_gateway.journal import Event

from ..contracts import (
    WorldCandidate,
    WorldDuplicateTitle,
    WorldEdge,
    WorldNode,
    WorldObjectiveBeacon,
    WorldParseMiss,
    WorldProjection,
)

WorldRow = tuple[int, str, str | None, str | dict[str, Any]]


def project_world(
    database: Path,
    through_sequence: int | None = None,
    objective: str | None = None,
) -> WorldProjection:
    """Project distinct places and observed transitions from a read-only DB."""

    if not database.is_file():
        return _empty()
    connection = sqlite3.connect(
        f"file:{database.resolve()}?mode=ro",
        uri=True,
    )
    try:
        if through_sequence is None:
            rows = connection.execute(
                "SELECT seq, kind, trace_id, payload "
                "FROM events ORDER BY seq"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT seq, kind, trace_id, payload "
                "FROM events WHERE seq <= ? ORDER BY seq",
                (through_sequence,),
            ).fetchall()
    finally:
        connection.close()
    return _project(rows, objective=objective)


def project_world_events(
    events: Iterable[Event],
    objective: str | None = None,
) -> WorldProjection:
    """Project the same contract from one in-memory gateway prefix."""

    rows = (
        (
            event.seq,
            event.kind,
            event.trace_id,
            event.payload,
        )
        for event in events
    )
    return _project(rows, objective=objective)


def _project(
    rows: Iterable[WorldRow],
    *,
    objective: str | None = None,
) -> WorldProjection:
    commands: dict[str, str] = {}
    rooms: dict[str, dict[str, Any]] = {}
    places: dict[int, dict[str, Any]] = {}
    visits: Counter[int] = Counter()
    visit_evidence: dict[int, list[int]] = defaultdict(list)
    transitions: dict[tuple[int, int, str], list[int]] = defaultdict(list)
    last_place: int | None = None
    current_title: str | None = None
    current_confidence = "unknown"
    unknown_positions = 0
    miss_rate = 0.0
    parse_misses: list[WorldParseMiss] = []
    ambiguous_exits: tuple[str, ...] = ()
    ambiguous_sequence: int | None = None
    ambiguous_method = "candidate"
    explicit_candidates: tuple[int, ...] = ()

    for seq, kind, trace_id, encoded in rows:
        payload = _payload(encoded)
        if payload is None:
            continue
        if kind == "command" and trace_id:
            line = str(payload.get("line", ""))
            commands[trace_id] = line.split()[0].casefold() if line else ""
        elif (
            kind == "observation"
            and payload.get("kind") == "room"
            and trace_id
        ):
            rooms[trace_id] = payload
        elif kind == "parse_metric":
            miss_rate = float(payload.get("cumulative_miss_rate", miss_rate))
        elif kind == "unparsed":
            parse_misses.append(
                WorldParseMiss(
                    sequence=int(seq),
                    trace_id=trace_id,
                    reason=_miss_reason(payload),
                )
            )
        elif kind == "position":
            place_value = payload.get("place")
            current_title = (
                str(payload["title"])
                if payload.get("title") is not None
                else None
            )
            current_confidence = str(payload.get("confidence", "unknown"))
            if not isinstance(place_value, int):
                unknown_positions += 1
                ambiguous_sequence = int(seq)
                ambiguous_method = str(payload.get("method", "candidate"))
                room = rooms.get(str(trace_id), {})
                ambiguous_exits = tuple(
                    str(item) for item in room.get("exits", ())
                )
                explicit_candidates = tuple(
                    int(candidate)
                    for candidate in payload.get("candidates", ())
                    if str(candidate).isdigit()
                )
                last_place = None
                continue
            room = rooms.get(str(trace_id), {})
            exits = tuple(str(item) for item in room.get("exits", ()))
            place = places.setdefault(
                place_value,
                {
                    "title": current_title or "Unknown place",
                    "exits": exits,
                    "mobs": tuple(str(item) for item in room.get("mobs", ())),
                    "objects": tuple(
                        str(item) for item in room.get("objects", ())
                    ),
                    "first_seq": int(seq),
                    "last_seq": int(seq),
                    "confidence": current_confidence,
                    "method": str(payload.get("method", "unknown")),
                },
            )
            place["last_seq"] = int(seq)
            place["confidence"] = current_confidence
            place["method"] = str(payload.get("method", "unknown"))
            if exits:
                place["exits"] = exits
            if room.get("mobs"):
                place["mobs"] = tuple(
                    str(item) for item in room.get("mobs", ())
                )
            if room.get("objects"):
                place["objects"] = tuple(
                    str(item) for item in room.get("objects", ())
                )
            visits[place_value] += 1
            visit_evidence[place_value].append(int(seq))
            if last_place is not None and last_place != place_value:
                direction = commands.get(str(trace_id), "unknown")
                transitions[(last_place, place_value, direction)].append(
                    int(seq)
                )
            last_place = place_value

    candidate_places: set[int] = set()
    if current_confidence == "ambiguous" and current_title is not None:
        candidate_places = {
            place
            for place, data in places.items()
            if str(data["title"]).casefold() == current_title.casefold()
        }
        if explicit_candidates:
            candidate_places = set(explicit_candidates)
            for place in explicit_candidates:
                places.setdefault(
                    place,
                    {
                        "title": current_title,
                        "exits": (),
                        "mobs": (),
                        "objects": (),
                        "first_seq": ambiguous_sequence or 0,
                        "last_seq": ambiguous_sequence or 0,
                        "confidence": "ambiguous",
                        "method": ambiguous_method,
                    },
                )

    current_place = (
        last_place
        if last_place is not None
        and current_confidence not in {"ambiguous", "unknown"}
        else None
    )
    nodes = tuple(
        WorldNode(
            id=f"place:{place}",
            place=place,
            title=str(data["title"]),
            exits=tuple(data["exits"]),
            mobs=tuple(data.get("mobs", ())),
            objects=tuple(data.get("objects", ())),
            visits=visits[place],
            evidence=tuple(visit_evidence[place]),
            first_seq=int(data["first_seq"]),
            last_seq=int(data["last_seq"]),
            state=(
                "current"
                if place == current_place
                else "candidate"
                if place in candidate_places
                else "observed"
            ),
            confidence=str(data["confidence"]),
            method=str(data["method"]),
        )
        for place, data in sorted(
            places.items(),
            key=lambda item: (int(item[1]["first_seq"]), item[0]),
        )
    )
    edges = tuple(
        WorldEdge(
            id=f"{source}:{target}:{direction}",
            source=f"place:{source}",
            target=f"place:{target}",
            direction=direction,
            traversals=len(sequences),
            evidence=tuple(sequences),
        )
        for (source, target, direction), sequences in sorted(
            transitions.items(),
            key=lambda item: item[1][0],
        )
    )
    candidate_details = tuple(
        _candidate(
            place,
            places[place],
            ambiguous_exits,
            visit_evidence[place],
            ambiguous_sequence,
        )
        for place in sorted(candidate_places)
    )
    duplicate_titles = _duplicates(places)
    objective_beacons = _objective_beacons(
        objective,
        places,
        visit_evidence,
    )
    return WorldProjection(
        nodes=nodes,
        edges=edges,
        current_title=current_title,
        current_confidence=current_confidence,
        candidates=tuple(
            f"place:{place}" for place in sorted(candidate_places)
        ),
        candidate_details=candidate_details,
        duplicate_titles=duplicate_titles,
        objective_beacons=objective_beacons,
        parse_miss_rate=miss_rate,
        parse_misses=tuple(parse_misses),
        unknown_positions=unknown_positions,
    )


def _candidate(
    place: int,
    data: dict[str, Any],
    observed_exits: tuple[str, ...],
    evidence: list[int],
    ambiguous_sequence: int | None,
) -> WorldCandidate:
    candidate_exits = tuple(str(item) for item in data["exits"])
    supporting = tuple(
        sorted(set(observed_exits) & set(candidate_exits))
    )
    conflicting = (
        tuple(sorted(set(observed_exits) ^ set(candidate_exits)))
        if observed_exits and candidate_exits
        else ()
    )
    return WorldCandidate(
        node_id=f"place:{place}",
        title=str(data["title"]),
        supporting_exits=supporting,
        conflicting_exits=conflicting,
        reason=_candidate_reason(observed_exits, candidate_exits),
        evidence=tuple(
            sequence
            for sequence in (*evidence, ambiguous_sequence)
            if sequence is not None
        ),
    )


def _duplicates(
    places: dict[int, dict[str, Any]],
) -> tuple[WorldDuplicateTitle, ...]:
    titles: dict[str, list[int]] = defaultdict(list)
    rendered: dict[str, str] = {}
    for place, data in places.items():
        folded = str(data["title"]).casefold()
        titles[folded].append(place)
        rendered.setdefault(folded, str(data["title"]))
    return tuple(
        WorldDuplicateTitle(
            title=rendered[folded],
            node_ids=tuple(
                f"place:{place}" for place in sorted(group)
            ),
        )
        for folded, group in sorted(titles.items())
        if len(group) > 1
    )


def _payload(
    encoded: str | dict[str, Any],
) -> dict[str, Any] | None:
    if isinstance(encoded, dict):
        return encoded
    try:
        value = json.loads(encoded)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _candidate_reason(
    observed: tuple[str, ...],
    candidate: tuple[str, ...],
) -> str:
    if not observed:
        return (
            "The latest room exposed no exits, so title evidence cannot "
            "separate it."
        )
    if not candidate:
        return "This candidate has no retained exit signature to compare."
    if set(observed) == set(candidate):
        return "The title and complete exit signature both match."
    if set(observed) & set(candidate):
        return "The title and part of the exit signature match."
    return "Only the duplicate title matches, while the retained exits conflict."


def _miss_reason(payload: dict[str, Any]) -> str:
    for key in ("reason", "text", "preview", "line"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:240]
    return "Gateway retained unparsed text without a structured reason."


def _empty() -> WorldProjection:
    return WorldProjection(
        nodes=(),
        edges=(),
        current_title=None,
        current_confidence="unknown",
        candidates=(),
        candidate_details=(),
        duplicate_titles=(),
        objective_beacons=(),
        parse_miss_rate=0,
        parse_misses=(),
        unknown_positions=0,
    )


def _objective_beacons(
    objective: str | None,
    places: dict[int, dict[str, Any]],
    evidence: dict[int, list[int]],
) -> tuple[WorldObjectiveBeacon, ...]:
    if objective is None:
        return ()
    normalized_objective = _normalize_entity(objective)
    beacons: list[WorldObjectiveBeacon] = []
    for place, data in places.items():
        sightings = (
            tuple(data.get("mobs", ()))
            + tuple(data.get("objects", ()))
        )
        for sighting in sightings:
            normalized_sighting = _normalize_entity(str(sighting))
            if (
                len(normalized_sighting) < 4
                or normalized_sighting not in normalized_objective
            ):
                continue
            beacons.append(
                WorldObjectiveBeacon(
                    node_id=f"place:{place}",
                    label=str(sighting),
                    reason=(
                        "A retained room observation places this objective "
                        "entity here."
                    ),
                    evidence=tuple(evidence[place]),
                )
            )
    return tuple(beacons)


def _normalize_entity(value: str) -> str:
    words = [
        "".join(character for character in word.casefold() if character.isalnum())
        for word in value.split()
    ]
    return " ".join(
        word for word in words if word and word not in {"a", "an", "the"}
    )
