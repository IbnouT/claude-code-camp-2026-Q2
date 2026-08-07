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
    here = graph.room_of(place_id)
    for entry in _seen(store, graph):
        if entry["room"] != here:
            continue
        kind = {"mob": "creature", "object": "object"}.get(
            entry["kind"], "something"
        )
        again = "" if entry["times"] < 2 else f" (seen {entry['times']} times)"
        lines.append(f"  {kind} here: {entry['name']}{again}")
    for fact in store.current_facts(layer="belief"):
        if not fact.predicate.startswith("model."):
            continue
        if graph.room_of(fact.subject) != here:
            continue
        lines.append(
            f"  you noted ({fact.predicate.removeprefix('model.')}): "
            f"{fact.value}"
        )
    here = graph.room_of(place_id)
    refused = [
        fact.predicate.removeprefix("passage.")
        for fact in store.current_facts(layer="parsed")
        if fact.predicate.startswith("passage.")
        and fact.value == "refused"
        and graph.room_of(fact.subject) == here
    ]
    for direction in sorted(refused):
        lines.append(f"  {direction}: would not open when tried")
    return "\n".join(lines)


def _seen(store: Any, graph: WorldGraph) -> list[dict]:
    """What has been seen, folded to one entry per thing per room.

    Every look records a fresh sighting, so a corridor walked ten times
    holds ten sightings of the same guard. Reporting them one by one
    fills the answer with repetition and pushes everything else out, so
    the same thing in the same room becomes one entry with a count.
    """
    entries: dict[str, dict[str, Any]] = {}
    for layer in ("learned", "belief"):
        for fact in store.current_facts(layer=layer):
            if not fact.subject.startswith(("room-sighting:", "sighting:")):
                continue
            if fact.predicate in ("name", "kind", "room"):
                entries.setdefault(fact.subject, {})[fact.predicate] = fact.value
    folded: dict[tuple, dict] = {}
    for entry in entries.values():
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        room = graph.room_of(entry.get("room"))
        key = (room, name.casefold(), entry.get("kind"))
        found = folded.setdefault(key, {
            "name": name,
            "kind": entry.get("kind"),
            "room": room,
            "times": 0,
        })
        found["times"] += 1
    return sorted(
        folded.values(), key=lambda item: (-item["times"], item["name"])
    )


def _listed(lines: list[str]) -> str:
    """At most a screenful, saying plainly when there is more."""
    if len(lines) <= LIMIT:
        return "\n".join(lines)
    return "\n".join(lines[:LIMIT] + [f"and {len(lines) - LIMIT} more"])


def _creatures(
    store: Any,
    graph: WorldGraph,
    name: str | None,
    only_named: bool = False,
) -> str:
    """Creatures seen, and where. An object is not a creature."""
    wanted = (name or "").casefold()
    lines = []
    for entry in _seen(store, graph):
        # Only what was recorded as a creature. A sighting of unknown kind
        # is not offered as one: answering an object when asked for
        # creatures is how this answer became useless before.
        if entry["kind"] != "mob":
            continue
        if wanted and wanted not in entry["name"].casefold():
            continue
        lines.append(f"{entry['name']} at {_title(graph, entry['room'])}")
    if not lines:
        if only_named and name:
            return f"you have not seen anything called {name!r}"
        return "you have not seen any creature yet"
    return _listed(lines)


def _services(store: Any, graph: WorldGraph) -> str:
    lines = []
    for fact in sorted(_facts(store), key=lambda f: f.predicate):
        if not fact.predicate.startswith("service."):
            continue
        kind = fact.predicate.removeprefix("service.")
        lines.append(f"{kind} at {_title(graph, fact.subject)}")
    return _listed(lines) or "you have not recorded any service yet"


def _unexplored(graph: WorldGraph, place_id: str | None) -> str:
    """Where there is still ground, nearest first."""
    from .navigation.route import plan_route

    frontier = graph.frontier_rooms()
    if not frontier:
        return "every exit you know about has been walked"
    here = graph.room_of(place_id)
    measured = []
    for room in frontier:
        steps = None
        if here is not None and here in graph.rooms:
            plan = plan_route(graph, here, room.place_id)
            steps = None if plan is None else plan.moves
        measured.append((steps if steps is not None else 10**6, steps, room))
    measured.sort(key=lambda item: (item[0], item[2].title or ""))
    lines = []
    for _rank, steps, room in measured:
        ways = ", ".join(sorted(room.frontier()))
        if steps == 0:
            where = "right here"
        elif steps is None:
            where = "no known way there"
        else:
            where = f"{steps} steps away"
        lines.append(f"{room.title or 'a place'} ({where}): {ways} not walked")
    return _listed(lines)


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
    if "mana" in state:
        top = state.get("max_mana")
        lines.append(f"mana {state['mana']}" + (f" of {top}" if top else ""))
    for name in ("level", "exp", "gold"):
        if name in state:
            lines.append(f"{name} {state[name]}")
    if state.get("posture"):
        lines.append(str(state["posture"]))
    for name in ("hungry", "thirsty", "drunk", "poisoned"):
        if state.get(name):
            lines.append(f"you are {name}")
    # Said plainly rather than left out: an answer that omits what it does
    # not know reads as an answer that says there is nothing to know.
    lines.append("what you carry and can do is not recorded yet")
    return ", ".join(lines)
