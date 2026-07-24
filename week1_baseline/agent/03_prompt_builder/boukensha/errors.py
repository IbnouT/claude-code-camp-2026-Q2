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
