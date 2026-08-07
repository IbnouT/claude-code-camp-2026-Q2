"""Answering what the agent knows, in words it can act on.

Storing what was seen is useless if nothing can read it back. These are
the questions worth asking before deciding what to do next, each
answered from the store and rendered as short lines rather than rows,
because the reader is a model choosing an action, not a database client.
"""

from __future__ import annotations

from typing import Any, Sequence

from .navigation.graph import WorldGraph

QUESTIONS = ("here", "creatures", "services", "target", "unexplored", "self")
LIMIT = 12


def answer(
    store: Any,
    graph: WorldGraph,
    question: str,
    *,
    place_id: str | None = None,
    name: str | None = None,
    player_id: str = "",
) -> str:
    """Answer one question about what is known. Never guesses."""
    if question == "here":
        return _here(store, graph, place_id)
    if question == "creatures":
        return _creatures(store, graph, name)
    if question == "services":
        return _services(store, graph)
    if question == "target":
        return _creatures(store, graph, name, only_named=True)
    if question == "unexplored":
        return _unexplored(graph, place_id)
    if question == "self":
        return _self(store, player_id)
    return f"nothing asks {question!r}; ask one of: {', '.join(QUESTIONS)}"


def _facts(store: Any, layers: Sequence[str] = ("learned", "belief")) -> list:
    found = []
    for layer in layers:
        found.extend(store.current_facts(layer=layer))
    return found


def _title(graph: WorldGraph, place_id: str | None) -> str:
    room = graph.rooms.get(graph.room_of(place_id)) if place_id else None
    return room.title if room is not None and room.title else "somewhere"


def _here(store: Any, graph: WorldGraph, place_id: str | None) -> str:
    room = graph.rooms.get(graph.room_of(place_id)) if place_id else None
    if room is None:
        return "this place is not in what you have mapped yet"
    lines = [f"{room.title or 'here'}:"]
    for direction in sorted(room.exits):
        target = room.links.get(direction)
        if target is None:
            lines.append(f"  {direction}: not walked yet")
        else:
            known = graph.rooms.get(target)
            lines.append(
                f"  {direction}: {known.title if known else 'somewhere known'}"
            )
    seen = _sightings_at(store, graph, graph.room_of(place_id))
    for what in seen[:LIMIT]:
        lines.append(f"  seen here: {what}")
    refused = [
        fact.predicate.removeprefix("passage.")
        for fact in _facts(store)
        if fact.subject == place_id
        and fact.predicate.startswith("passage.")
        and fact.value == "refused"
    ]
    for direction in sorted(refused):
        lines.append(f"  {direction}: would not open when tried")
    return "\n".join(lines)


def _sightings_at(store: Any, graph: WorldGraph, room: str | None) -> list[str]:
    names: dict[str, str] = {}
    rooms: dict[str, str] = {}
    for fact in _facts(store):
        if not fact.subject.startswith(("room-sighting:", "sighting:")):
            continue
        if fact.predicate == "name" and isinstance(fact.value, str):
            names[fact.subject] = fact.value
        elif fact.predicate == "room" and isinstance(fact.value, str):
            rooms[fact.subject] = fact.value
    return sorted(
        name for subject, name in names.items()
        if room is None or graph.room_of(rooms.get(subject)) == room
    )


def _creatures(
    store: Any,
    graph: WorldGraph,
    name: str | None,
    only_named: bool = False,
) -> str:
    names: dict[str, str] = {}
    rooms: dict[str, str] = {}
    for fact in _facts(store):
        if not fact.subject.startswith(("room-sighting:", "sighting:")):
            continue
        if fact.predicate == "name" and isinstance(fact.value, str):
            names[fact.subject] = fact.value
        elif fact.predicate == "room" and isinstance(fact.value, str):
            rooms[fact.subject] = fact.value
    wanted = (name or "").casefold()
    lines = []
    for subject, seen in sorted(names.items(), key=lambda item: item[1]):
        if wanted and wanted not in seen.casefold():
            continue
        where = _title(graph, rooms.get(subject))
        lines.append(f"{seen} at {where}")
    if not lines:
        if only_named and name:
            return f"you have not seen anything called {name!r}"
        return "you have not seen any creature yet"
    return "\n".join(lines[:LIMIT])


def _services(store: Any, graph: WorldGraph) -> str:
    lines = []
    for fact in sorted(_facts(store), key=lambda f: f.predicate):
        if not fact.predicate.startswith("service."):
            continue
        kind = fact.predicate.removeprefix("service.")
        lines.append(f"{kind} at {_title(graph, fact.subject)}")
    return "\n".join(lines[:LIMIT]) or "you have not recorded any service yet"


def _unexplored(graph: WorldGraph, place_id: str | None) -> str:
    frontier = graph.frontier_rooms()
    if not frontier:
        return "every exit you know about has been walked"
    lines = []
    for room in frontier[:LIMIT]:
        ways = ", ".join(sorted(room.frontier()))
        lines.append(f"{room.title or 'a place'}: {ways} not walked yet")
    return "\n".join(lines)


def _self(store: Any, player_id: str) -> str:
    subject = f"player:{player_id}"
    state = {
        fact.predicate.removeprefix("state."): fact.value
        for fact in store.current_facts(layer="parsed")
        if fact.subject == subject and fact.predicate.startswith("state.")
    }
    if not state:
        return "you have not looked at yourself yet"
    lines = []
    if "hit" in state:
        top = state.get("max_hit")
        lines.append(
            f"health {state['hit']}" + (f" of {top}" if top else "")
        )
    if "move" in state:
        top = state.get("max_move")
        lines.append(
            f"movement {state['move']}" + (f" of {top}" if top else "")
        )
    for name in ("level", "exp", "gold"):
        if name in state:
            lines.append(f"{name} {state[name]}")
    for name in ("hungry", "thirsty"):
        if state.get(name):
            lines.append(f"you are {name}")
    return ", ".join(lines)
