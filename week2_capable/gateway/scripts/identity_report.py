"""Measure the room identity rule against a knowledge store.

    uv run python scripts/identity_report.py <knowledge.db>

Reports how many observed places fold into rooms, how many rooms span
more than one session, and the largest connected piece of the joined
map. Every number here is reproducible from the store it names.
"""

from __future__ import annotations

import collections
import pathlib
import sys

from mud_gateway.identity import places_from_facts, resolve
from mud_gateway.knowledge import KnowledgeStore


def main() -> int:
    path = pathlib.Path(sys.argv[1])
    player = sys.argv[2] if len(sys.argv) > 2 else path.parent.name
    store = KnowledgeStore(path, player_id=player, read_only=True)
    places = places_from_facts(store.current_facts(layer="learned"))
    bindings = resolve(places)
    corroborated_rooms = {
        b.room_id for b in bindings if b.confidence == "confirmed"
    }
    store.close()

    rooms = {b.place_id: b.room_id for b in bindings}
    members = collections.defaultdict(list)
    for place_id, room in rooms.items():
        members[room].append(place_id)
    by_id = {p.place_id: p for p in places}
    sessions = {
        room: {by_id[p].session for p in ids} for room, ids in members.items()
    }
    joined = sum(1 for ids in members.values() if len(ids) > 1)
    multi = sum(1 for s in sessions.values() if len(s) > 1)

    edges = collections.defaultdict(set)
    for place in places:
        here = rooms.get(place.place_id)
        for target in place.links.values():
            there = rooms.get(target)
            if here and there and here != there:
                edges[here].add(there)
                edges[there].add(here)
    seen: set[str] = set()
    largest = 0
    for room in members:
        if room in seen:
            continue
        stack, size = [room], 0
        seen.add(room)
        while stack:
            node = stack.pop()
            size += 1
            for neighbour in edges[node] - seen:
                seen.add(neighbour)
                stack.append(neighbour)
        largest = max(largest, size)

    titles = collections.Counter(p.title for p in places)
    print(f"places            : {len(places)}")
    print(f"distinct titles   : {len(titles)}")
    print(f"rooms after rule  : {len(members)}")
    print(f"places joined     : {sum(len(i) for i in members.values() if len(i) > 1)}"
          f" ({100 * sum(len(i) for i in members.values() if len(i) > 1) / max(len(places), 1):.0f}%)")
    print(f"rooms with >1 place: {joined}")
    print(f"rooms spanning sessions: {multi}")
    print(f"largest connected piece: {largest} of {len(members)} rooms")
    confirmed = sum(1 for b in bindings if b.confidence == "confirmed")
    print(f"places by evidence : {confirmed} corroborated, "
          f"{len(bindings) - confirmed} uncontested")
    unsupported = [
        room for room, ids in members.items()
        if len(ids) > 1 and room not in corroborated_rooms
    ]
    print(f"merged rooms with no agreeing exit: {len(unsupported)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
