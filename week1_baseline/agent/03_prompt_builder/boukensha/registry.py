"""Registry: holds the agent's tools and dispatches a call to its handler.

The registry owns the tool table outright. Registration, lookup, and dispatch
all live here, so no other component reaches through to find a tool.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from .errors import ToolArgumentError, UnknownToolError
from .tool import Tool


class Registry:
    """A ``name -> Tool`` table with registration and dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # -- registration ------------------------------------------------------

    def register(self, tool: Tool) -> Tool:
        """Add an already-built tool. A duplicate name is rejected."""
        if tool.name in self._tools:
            raise ValueError(f"a tool named '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        return tool

    def tool(self, name: str, description: str,
             parameters: dict[str, Any] | None = None) -> Callable[[Callable], Callable]:
        """Decorator: build a tool from the function and register it.

        The decorated function is returned unchanged.
        """
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.register(Tool(name, description, parameters or {}, handler))
            return handler
        return decorator

    # -- lookup ------------------------------------------------------------

    @property
    def tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    # -- dispatch ----------------------------------------------------------

    def dispatch(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Run a tool by name with keyword arguments, returning its result."""
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"no tool registered as '{name}'")

        args = args or {}
        undeclared = [a for a in args if a not in tool.parameters]
        if undeclared:
            raise ToolArgumentError(
                f"tool '{name}' got undeclared argument(s): "
                f"{', '.join(sorted(undeclared))}"
            )

        # Check the arguments bind to the handler's signature (this catches a
        # missing required argument) before invoking. The handler then runs
        # outside the check, so a TypeError raised inside its own body is a
        # real bug and propagates honestly, never relabeled as an argument
        # error.
        try:
            inspect.signature(tool.handler).bind(**args)
        except TypeError as exc:
            raise ToolArgumentError(f"tool '{name}': {exc}") from exc

        return tool.handler(**args)

    def __str__(self) -> str:
        return f"<Registry tools={sorted(self._tools)}>"

    __repr__ = __str__
