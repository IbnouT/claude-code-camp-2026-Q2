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

    ``required`` optionally overrides which parameters the wire schema marks
    required. Left ``None``, required-ness derives from the handler signature
    (a parameter with no default is required), which is right for every
    signature-declared tool. A ``**kwargs`` handler accepts anything, so
    signature derivation would mark every parameter required. MCP-derived tools
    use ``**kwargs`` and pass their server's ``inputSchema.required`` here, so
    only genuinely required parameters are marked, and optional ones are not
    falsely required.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    required: frozenset[str] | None = None

    def __post_init__(self) -> None:
        self._check_schema_matches_handler()
        self._check_required_declared()

    def _check_required_declared(self) -> None:
        if self.required is None:
            return
        unknown = self.required - set(self.parameters)
        if unknown:
            raise ValueError(
                f"tool '{self.name}': required parameter(s) "
                f"{', '.join(sorted(unknown))} not declared in parameters "
                f"(the model cannot supply a parameter it was never shown)"
            )

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

    @property
    def required_parameters(self) -> list[str]:
        """The parameters marked required in the wire schema, in declared order.

        With an explicit ``required`` set, the declared parameters that are in
        it. Otherwise, declared parameters whose handler argument has no
        default.
        """
        if self.required is not None:
            return [name for name in self.parameters if name in self.required]
        try:
            sig = inspect.signature(self.handler)
        except (ValueError, TypeError):
            return list(self.parameters)
        required = []
        for name in self.parameters:
            param = sig.parameters.get(name)
            if param is None or param.default is inspect.Parameter.empty:
                required.append(name)
        return required

    def __str__(self) -> str:
        desc = self.description if len(self.description) <= 45 else self.description[:42] + "..."
        return f"<Tool name={self.name} description={desc!r} params={list(self.parameters)}>"

    __repr__ = __str__
