"""Validated structured objective metadata for one agent runtime."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

MAX_OBJECTIVE_TEXT = 4_000
ObjectiveSource = Literal["benchmark", "operator"]


@dataclass(frozen=True)
class ObjectiveContext:
    """The authored meaning retained beside the exact task prompt."""

    title: str
    clue: str | None
    source_kind: ObjectiveSource
    revision: int

    @classmethod
    def create(
        cls,
        task: str,
        *,
        title: str | None = None,
        clue: str | None = None,
        source_kind: ObjectiveSource = "operator",
        revision: int = 1,
    ) -> ObjectiveContext:
        clean_title = (title or task).strip()
        clean_clue = clue.strip() if clue and clue.strip() else None
        if not clean_title:
            raise ValueError("objective title cannot be empty")
        if len(clean_title) > MAX_OBJECTIVE_TEXT:
            raise ValueError("objective title is too long")
        if clean_clue is not None and len(clean_clue) > MAX_OBJECTIVE_TEXT:
            raise ValueError("objective clue is too long")
        if source_kind not in {"benchmark", "operator"}:
            raise ValueError(f"unsupported objective source {source_kind!r}")
        if revision < 1:
            raise ValueError("objective revision must be positive")
        return cls(
            title=clean_title,
            clue=clean_clue,
            source_kind=source_kind,
            revision=revision,
        )

    def encode(self) -> str:
        """Return a deterministic child-process representation."""
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def as_log(self) -> dict[str, str | int | None]:
        """Return the typed value retained in the session-start record."""
        return asdict(self)

    @classmethod
    def decode(cls, raw: str, *, task: str) -> ObjectiveContext:
        """Decode and validate the internal child-process representation."""
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("objective context is invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("objective context must be an object")
        return cls.create(
            task,
            title=value.get("title") if isinstance(value.get("title"), str) else None,
            clue=value.get("clue") if isinstance(value.get("clue"), str) else None,
            source_kind=(
                value.get("source_kind")
                if value.get("source_kind") in {"benchmark", "operator"}
                else "operator"
            ),
            revision=(
                value.get("revision")
                if isinstance(value.get("revision"), int)
                else 1
            ),
        )
