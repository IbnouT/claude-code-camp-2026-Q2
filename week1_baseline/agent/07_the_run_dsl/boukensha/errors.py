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
