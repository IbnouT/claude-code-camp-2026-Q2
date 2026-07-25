"""Exception types shared across components.

Defined in one place so no component reaches into another to raise a shared
error.
"""

from __future__ import annotations


class ConfigError(Exception):
    """A malformed configuration file, reported with the offending key."""


class UnknownToolError(Exception):
    """Dispatch was asked for a tool name that is not registered."""


class ToolArgumentError(Exception):
    """A tool was called with arguments that do not match its declaration."""


class ApiError(Exception):
    """A provider call failed for good: exhausted retries or a hard status."""


class LoopError(Exception):
    """The agent loop failed for a reason the caller must handle.

    Introduced with the loop for parity and a stable error family. The loop
    itself winds down rather than raising, so nothing raises this here; the
    REPL added in a later step is its first catcher.
    """


class TurnCancelled(Exception):
    """The user cancelled the in-flight turn (Esc in the TUI).

    Raised by the agent loop at its next iteration boundary once the cancel
    event is set, so the turn ends promptly without waiting out the remaining
    iterations. The REPL records the cancellation and keeps the session alive.
    """


class McpError(Exception):
    """The MCP client's transport or protocol broke.

    Raised when a server closes the pipe mid-request, returns a JSON-RPC error,
    or otherwise violates the exchange the client expects.
    """


class McpTimeoutError(McpError):
    """An MCP request exceeded its timeout with no response.

    A subclass of :class:`McpError`, so existing ``except McpError`` sites still
    catch it. The connection is left open, so unrelated calls to the same server
    keep working: only this one call is abandoned.
    """


class McpToolCollisionError(Exception):
    """Two tools resolve to one agent-side name.

    A config contradiction, never excused, not even for an optional server:
    silently dropping one tool is the expensive failure to debug. The message
    names the tool and points at the ``prefix:`` fix.
    """


class McpServerError(Exception):
    """A required MCP server failed to spawn or handshake, naming the server."""
