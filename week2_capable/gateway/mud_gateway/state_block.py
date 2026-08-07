"""What the agent is told about its situation, every turn.

A tool has to be chosen before it helps. This block is not chosen: it is
put in front of the agent on every decision, so what it holds is what the
agent can be relied on to know. Everything here is therefore something a
player would keep in their head while playing: where they are, what they
can see leads where, what is with them, how they are doing, and the
handful of habits worth keeping.

Rendered fresh from the store each time and never accumulated, so it can
never describe a situation that has passed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .navigation.graph import WorldGraph, canonical_direction

_ORDER = ("north", "east", "south", "west", "up", "down")


def render_state_block(
    store: Any,
    pipeline: Any,
    projector: Any,
    *,
    advice: str = "",
    player_id: str = "",
) -> str:
    """The situation as the agent should carry it into its next decision."""
    place_id = getattr(projector, "current_place_id", None)
    room = getattr(pipeline, "room", None)
    graph = WorldGraph.from_store(store)
    here = graph.room_of(place_id)
    known = graph.rooms.get(here) if here else None

    lines: list[str] = []
    title = _title(room, known)
    visits = _visits(store, graph, here)
    if title is None:
        lines.append("you have not seen where you are yet")
    elif visits > 1:
        lines.append(f"{title} — you have been here {visits} times")
    else:
        lines.append(f"{title} — first time here")

    for line in _ways(store, graph, room, known, here):
        lines.append(f"  {line}")

    for line in _present(store, graph, here):
        lines.append(line)

    condition = _condition(store, pipeline, player_id)
    if condition:
        lines.append(condition)

    lines.append(
        f"map: {len(graph.rooms)} rooms · "
        f"{len(graph.frontier_rooms())} with ways not yet walked"
    )
    for line in _notes(store, graph, here):
        lines.append(line)
    if advice:
        lines.append(advice)
    return "\n".join(lines)


def _title(room: Any, known: Any) -> str | None:
    if room is not None and room.title:
        return str(room.title)
    if known is not None and known.title:
        return str(known.title)
    return None


def _visits(store: Any, graph: WorldGraph, here: str | None) -> int:
    """How many observed places this room has been seen as."""
    if here is None:
        return 0
    return sum(
        1 for place, room in graph.identity.items() if room == here
    ) or 1


def _ways(
    store: Any,
    graph: WorldGraph,
    room: Any,
    known: Any,
    here: str | None,
) -> list[str]:
    """Each way out, and what is known about where it goes."""
    raw: Sequence[str] = ()
    if room is not None and room.exits:
        raw = tuple(room.exits)
    elif known is not None:
        raw = tuple(sorted(known.exits))
    links = dict(known.links) if known is not None else {}
    refused = {
        fact.predicate.removeprefix("passage."): fact.value
        for fact in store.current_facts(layer="parsed")
        if fact.predicate.startswith("passage.")
        and graph.room_of(fact.subject) == here
    }
    told = {
        fact.predicate.removeprefix("exit_named."): str(fact.value)
        for fact in store.current_facts(layer="learned")
        if fact.predicate.startswith("exit_named.")
        and graph.room_of(fact.subject) == here
    }
    ordered = sorted(
        {d for d in (canonical_direction(str(r)) for r in raw) if d},
        key=lambda d: _ORDER.index(d) if d in _ORDER else len(_ORDER),
    )
    lines = []
    for direction in sorted(set(ordered) | set(told),
                            key=lambda d: _ORDER.index(d)
                            if d in _ORDER else len(_ORDER)):
        target = links.get(direction)
        named = told.get(direction)
        if target is not None:
            room_there = graph.rooms.get(target)
            walked = (
                room_there.title
                if room_there is not None and room_there.title
                else "somewhere already mapped"
            )
            # The game named one room and the walk found another. Say so
            # rather than pick: it means the way changed, or two rooms
            # share a name, and either is worth knowing.
            if named and named.casefold() != walked.casefold():
                where = f"{walked} (the game calls it {named})"
            else:
                where = walked
        elif refused.get(direction) == "refused":
            where = "would not open when tried"
        elif named:
            where = f"{named}, never walked"
        else:
            where = "not walked yet"
        lines.append(f"{direction} → {where}")
    return lines


def _present(store: Any, graph: WorldGraph, here: str | None) -> list[str]:
    """What has been seen in this room, creatures before things."""
    from .recall import _seen

    lines = []
    for entry in _seen(store, graph):
        if entry["room"] != here:
            continue
        kind = {"mob": "creature", "object": "object"}.get(
            entry["kind"], "something"
        )
        lines.append(f"here: {entry['name']} ({kind})")
    return lines[:6]


def _condition(store: Any, pipeline: Any, player_id: str) -> str:
    """How the character is doing, in the terms a fight is decided on."""
    state = {
        fact.predicate.removeprefix("state."): fact.value
        for fact in store.current_facts(layer="parsed")
        if fact.subject == f"player:{player_id}"
        and fact.predicate.startswith("state.")
    }
    vitals = getattr(pipeline, "vitals", None)
    parts = []
    if vitals is not None:
        top = state.get("max_hit")
        parts.append(f"{vitals.hit}{f'/{top}' if top else ''}hp")
        top_move = state.get("max_move")
        parts.append(f"{vitals.move}{f'/{top_move}' if top_move else ''}mv")
    for name, label in (("level", "level"), ("gold", "gold")):
        if name in state:
            parts.append(f"{label} {state[name]}")
    for name in ("hungry", "thirsty", "poisoned"):
        if state.get(name):
            parts.append(name)
    return "you: " + " · ".join(parts) if parts else ""


def _notes(store: Any, graph: WorldGraph, here: str | None) -> list[str]:
    """Anything the agent itself wrote down about this room."""
    lines = []
    for fact in store.current_facts(layer="belief"):
        if not fact.predicate.startswith("model."):
            continue
        if graph.room_of(fact.subject) != here:
            continue
        lines.append(
            f"you noted ({fact.predicate.removeprefix('model.')}): "
            f"{fact.value}"
        )
    return lines
