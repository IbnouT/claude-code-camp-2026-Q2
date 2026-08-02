"""Evidence-backed knowledge coverage for one investigation."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from ..contracts import (
    FrontierItem,
    Investigation,
    KnowledgeMetric,
    KnowledgeOverview,
)


def project_knowledge(investigation: Investigation) -> KnowledgeOverview:
    """Summarize recorded knowledge while keeping absent layers explicit."""

    world = investigation.world
    traversed: dict[str, set[str]] = defaultdict(set)
    for edge in world.edges:
        traversed[edge.source].add(edge.direction)

    frontier: list[FrontierItem] = []
    for node in world.nodes:
        for direction in node.exits:
            if direction not in traversed[node.id]:
                frontier.append(
                    FrontierItem(
                        id=f"{node.id}:{direction}",
                        title=f"{node.title} · {direction}",
                        kind="untraversed_exit",
                        detail="Observed exit with no recorded traversal.",
                        citations=(f"gateway:position:{node.last_seq}",),
                    )
                )
    for candidate in world.candidates:
        frontier.append(
            FrontierItem(
                id=f"candidate:{candidate}",
                title=candidate,
                kind="unresolved_position",
                detail="Candidate remains possible at the final evidence prefix.",
            )
        )

    state: Literal["partial", "unavailable"] = (
        "partial" if world.nodes else "unavailable"
    )
    missing = ["entities", "player", "progression", "durable knowledge store"]
    return KnowledgeOverview(
        state=state,
        source=(
            "Recorded run projection"
            if world.nodes
            else "No readable knowledge evidence"
        ),
        metrics=(
            KnowledgeMetric(
                label="Known places",
                value=len(world.nodes),
                detail="Distinct tracker place IDs in recorded evidence.",
            ),
            KnowledgeMetric(
                label="Observed transitions",
                value=len(world.edges),
                detail="Directed transitions supported by sequence evidence.",
            ),
            KnowledgeMetric(
                label="Open frontier",
                value=len(frontier),
                detail="Untraversed exits and unresolved final candidates.",
            ),
            KnowledgeMetric(
                label="Parse miss rate",
                value=world.parse_miss_rate,
                detail="Residual parser misses reported by the run.",
            ),
        ),
        frontier=tuple(frontier[:200]),
        entities=(),
        player={},
        progression=(),
        missing_layers=tuple(missing),
    )
