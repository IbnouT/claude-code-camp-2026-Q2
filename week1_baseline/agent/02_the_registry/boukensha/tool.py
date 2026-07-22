"""Tool: a callable capability the model can invoke.

A value object only. Registration and dispatch belong to the registry.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    """A named capability with a schema and a handler.

    The declared ``parameters`` are the schema the model is shown, and they
    must match the handler. A mismatch is checked at construction, so a tool
    that could never be called correctly never comes into existence. A schema
    that omits a required argument would otherwise hand the model an
    uncorrectable call: it cannot supply an argument it was never told about.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def __post_init__(self) -> None:
        self._check_schema_matches_handler()

    def _check_schema_matches_handler(self) -> None:
        try:
            sig = inspect.signature(self.handler)
        except (ValueError, TypeError):
            return  # some builtins expose no signature; nothing to check

        accepts_extra = any(
            p.kind is inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        positional_or_keyword = {
            name: p
            for name, p in sig.parameters.items()
            if p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }

        required = {
            name for name, p in positional_or_keyword.items()
            if p.default is inspect.Parameter.empty
        }
        missing = required - set(self.parameters)
        if missing:
            raise ValueError(
                f"tool '{self.name}': handler requires argument(s) "
                f"{', '.join(sorted(missing))} not declared in parameters"
            )

        if not accepts_extra:
            undeclared = set(self.parameters) - set(positional_or_keyword)
            if undeclared:
                raise ValueError(
                    f"tool '{self.name}': parameters declare "
                    f"{', '.join(sorted(undeclared))} not accepted by the handler"
                )

    def __str__(self) -> str:
        desc = self.description if len(self.description) <= 45 else self.description[:42] + "..."
        return f"<Tool name={self.name} description={desc!r} params={list(self.parameters)}>"

    __repr__ = __str__
