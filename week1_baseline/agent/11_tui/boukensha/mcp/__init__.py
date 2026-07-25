"""The MCP subpackage: a minimal MCP-over-stdio client.

Server-agnostic. The host layer in ``boukensha.tools.mcp`` turns a client's
discovered tools into boukensha tools.
"""

from .client import Client
from .transport import DEFAULT_TIMEOUT, StdioTransport, Transport

__all__ = ["Client", "Transport", "StdioTransport", "DEFAULT_TIMEOUT"]
