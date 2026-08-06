"""The knowledge capability's state block.

One compact, re-rendered summary of what the agent knows right now: the
observed place with its exits marked known or unexplored, live vitals
numbers, and position confidence. Rendered fresh from the store and the
pipeline's retained observations on every request, never accumulated.
"""

from __future__ import annotations

from typing import Any

from .navigation.graph import WorldGraph, canonical_direction


def render_state_block(
    store: Any,
    pipeline: Any,
    projector: Any,
) -> str:
    """Render the block, or an honest placeholder when nothing is known."""
    lines: list[str] = []
    place_id = getattr(projector, "current_place_id", None)
    room = getattr(pipeline, "room", None)
    graph = WorldGraph.from_store(store)
    known = graph.rooms.get(place_id) if place_id else None

    title = None
    if room is not None and room.title:
        title = room.title
    elif known is not None and known.title:
        title = known.title
    if title is not None:
        visits = ""
        lines.append(f"[here] {title}{visits}")
    else:
        lines.append("[here] position not yet observed")

    exits = _exit_marks(room, known)
    if exits:
        lines.append("exits: " + " | ".join(exits))

    vitals = getattr(pipeline, "vitals", None)
    if vitals is not None:
        lines.append(
            f"you: {vitals.hit}hp {vitals.mana}mana {vitals.move}mv"
        )

    frontier = len(graph.frontier_rooms())
    lines.append(
        f"map: {len(graph.rooms)} rooms known · "
        f"{frontier} with unexplored exits"
    )
    return "\n".join(lines)


def _exit_marks(room: Any, known: Any) -> list[str]:
    """Each live exit with a mark: ✓ leads to a known room, ? unexplored."""
    raw_exits: tuple[str, ...] = ()
    if room is not None and room.exits:
        raw_exits = tuple(room.exits)
    elif known is not None:
        raw_exits = tuple(sorted(known.exits))
    links = dict(known.links) if known is not None else {}
    marks = []
    for raw in raw_exits:
        direction = canonical_direction(str(raw))
        if direction is None:
            continue
        mark = "✓" if direction in links else "?"
        marks.append(f"{direction}{mark}")
    return marks
