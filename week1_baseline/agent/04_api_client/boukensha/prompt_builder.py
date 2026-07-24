"""PromptBuilder: binds a conversation, a backend, and a toolset.

A caller asks one object for a ready request instead of assembling the trio
itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from .backends.base import Backend
    from .context import Context
    from .tool import Tool


class PromptBuilder:
    """The request surface for one conversation on one backend."""

    def __init__(self, context: Context, backend: Backend,
                 tools: Sequence[Tool] = ()) -> None:
        self.context = context
        self.backend = backend
        self.tools = tuple(tools)

    def build_request(self, max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        return self.backend.build_request(
            self.context, self.tools, max_output_tokens, thinking
        )

    def headers(self) -> dict[str, str]:
        return self.backend.headers()

    def url(self) -> str:
        return self.backend.url()

    def __str__(self) -> str:
        return (
            f"<PromptBuilder backend={type(self.backend).__name__} "
            f"tools={[t.name for t in self.tools]}>"
        )

    __repr__ = __str__
