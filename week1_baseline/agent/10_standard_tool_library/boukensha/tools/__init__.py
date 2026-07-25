"""The tools subpackage.

Boukensha ships no built-in tools. The only member is the MCP host layer, which
turns any MCP server's advertised tools into boukensha tools.
"""

from . import mcp

__all__ = ["mcp"]
