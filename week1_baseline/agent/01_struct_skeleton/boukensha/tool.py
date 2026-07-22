"""Tool: a callable capability the model can invoke.

A value object only. Registration and dispatch belong to the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    """A named capability with a schema and a handler."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def __str__(self) -> str:
        desc = self.description if len(self.description) <= 45 else self.description[:42] + "..."
        return f"<Tool name={self.name} description={desc!r} params={list(self.parameters)}>"

    __repr__ = __str__
