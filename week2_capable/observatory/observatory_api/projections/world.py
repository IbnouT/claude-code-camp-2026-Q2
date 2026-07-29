"""Build an uncertainty-preserving world graph from a gateway journal."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..contracts import WorldEdge, WorldNode, WorldProjection


def project_world(database: Path) -> WorldProjection:
    """Project distinct places and observed transitions from a read-only DB."""

    if not database.is_file():
        return _empty()
    connection = sqlite3.connect(
        f"file:{database.resolve()}?mode=ro",
        uri=True,
    )
    try:
        rows = connection.execute(
            "SELECT seq, kind, trace_id, payload "
            "FROM events ORDER BY seq"
        ).fetchall()
    finally:
        connection.close()

    commands: dict[str, str] = {}
    rooms: dict[str, dict[str, Any]] = {}
    places: dict[int, dict[str, Any]] = {}
    visits: Counter[int] = Counter()
    transitions: dict[tuple[int, int, str], list[int]] = defaultdict(list)
    last_place: int | None = None
    current_title: str | None = None
    current_confidence = "unknown"
    unknown_positions = 0
    miss_rate = 0.0

    for seq, kind, trace_id, encoded in rows:
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
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
        elif kind == "position":
            place_value = payload.get("place")
            current_title = (
                str(payload["title"]) if payload.get("title") is not None else None
            )
            current_confidence = str(payload.get("confidence", "unknown"))
            if not isinstance(place_value, int):
                unknown_positions += 1
                last_place = None
                continue
            room = rooms.get(str(trace_id), {})
            exits = tuple(str(item) for item in room.get("exits", []))
            place = places.setdefault(
                place_value,
                {
                    "title": current_title or "Unknown place",
                    "exits": exits,
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
            visits[place_value] += 1
            if last_place is not None and last_place != place_value:
                direction = commands.get(str(trace_id), "unknown")
                transitions[(last_place, place_value, direction)].append(int(seq))
            last_place = place_value

    candidate_places = {
        place
        for place, data in places.items()
        if current_confidence == "ambiguous"
        and current_title is not None
        and str(data["title"]).casefold() == current_title.casefold()
    }
    current_place = (
        last_place
        if current_confidence in {"confirmed", "tracked"}
        else None
    )
    nodes = tuple(
        WorldNode(
            id=f"place:{place}",
            place=place,
            title=str(data["title"]),
            exits=tuple(data["exits"]),
            visits=visits[place],
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
            key=lambda item: int(item[1]["first_seq"]),
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
    return WorldProjection(
        nodes=nodes,
        edges=edges,
        current_title=current_title,
        current_confidence=current_confidence,
        candidates=tuple(f"place:{place}" for place in sorted(candidate_places)),
        parse_miss_rate=miss_rate,
        unknown_positions=unknown_positions,
    )


def _empty() -> WorldProjection:
    return WorldProjection(
        nodes=(),
        edges=(),
        current_title=None,
        current_confidence="unknown",
        candidates=(),
        parse_miss_rate=0,
        unknown_positions=0,
    )
