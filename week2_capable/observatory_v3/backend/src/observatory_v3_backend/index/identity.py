"""Versioned stable identity derived only from retained source anchors."""

from __future__ import annotations

import uuid
from typing import Literal

EntityKind = Literal[
    "session",
    "goal",
    "nudge",
    "turn",
    "iteration",
    "record",
    "trace",
    "experiment_sample",
]

IDENTITY_VERSION = 1
IDENTITY_NAMESPACE = uuid.UUID("814aad32-1ecc-578f-b5ce-aa70dd5a93bb")
ENTITY_KINDS: frozenset[str] = frozenset(
    {
        "session",
        "goal",
        "nudge",
        "turn",
        "iteration",
        "record",
        "trace",
        "experiment_sample",
    }
)


def stable_entity_id(
    session_id: str,
    kind: EntityKind,
    anchor: str,
) -> str:
    """Return the identity-contract v1 UUID for one retained source anchor."""
    if not session_id:
        raise ValueError("session identity cannot be empty")
    if kind not in ENTITY_KINDS:
        raise ValueError(f"unsupported entity kind {kind!r}")
    if not anchor:
        raise ValueError("source anchor cannot be empty")
    name = "\0".join(
        (
            "v1",
            _frame(session_id),
            _frame(kind),
            _frame(anchor),
        )
    )
    value = uuid.uuid5(IDENTITY_NAMESPACE, name)
    return f"obs1_{kind}_{value.hex}"


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"
