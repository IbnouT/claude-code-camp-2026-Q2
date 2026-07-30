"""Versioned, digestible reset baselines with no embedded credentials."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

TEMPLE = 3001
FED = 24
DEFAULT_FIELDS: dict[str, int] = {
    "level": 1,
    "exp": 0,
    "gold": 0,
    "bank": 0,
    "align": 0,
    "hunger": FED,
    "thirst": FED,
    "drunk": 0,
}


@dataclass(frozen=True)
class Baseline:
    """One immutable game-state target used by reset and comparison."""

    id: str
    version: int
    room: int
    fields: dict[str, int]

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def payload(self) -> dict[str, object]:
        return {
            **asdict(self),
            "digest": self.digest,
        }


LEVEL1_TEMPLE = Baseline(
    id="level1-temple",
    version=1,
    room=TEMPLE,
    fields=DEFAULT_FIELDS,
)
BASELINES = {LEVEL1_TEMPLE.id: LEVEL1_TEMPLE}


def baseline(baseline_id: str, version: int) -> Baseline:
    """Resolve an exact baseline identity or reject the request."""
    selected = BASELINES.get(baseline_id)
    if selected is None or selected.version != version:
        raise ValueError(
            f"unknown reset baseline {baseline_id!r} version {version}"
        )
    return selected
