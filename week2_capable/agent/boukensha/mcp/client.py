"""Client: a minimal MCP-over-stdio client.

Spawns an MCP server as a subprocess (via a :class:`~boukensha.mcp.transport.
StdioTransport`), performs the ``initialize`` handshake, and lets the caller
discover (``tools/list``) and call (``tools/call``) the tools it advertises. It
knows nothing about any particular server: ``command``, ``args``, and ``env`` are
the standard stdio transport config.

    client = Client.spawn("mud-manager", args=["--mcp"])
    for t in client.tools:
        print(t["name"])
    print(client.call_tool("look")["text"])
    client.close()

The client owns the JSON-RPC protocol; the transport owns the connection and
response correlation. Every exchange goes through :meth:`_request`, the single
place that assigns an id, applies the timeout, and turns a JSON-RPC ``error``
response into a raised :class:`McpError` instead of a silently empty result.

Wire format verified against the MCP specification 2025-06-18
(https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle and
.../server/tools): JSON-RPC 2.0 ``initialize`` (protocolVersion, capabilities,
clientInfo) then a ``notifications/initialized`` notification, then
``tools/list`` (tools carry name/description/inputSchema) and ``tools/call``
(result carries a ``content`` array of typed blocks and an ``isError`` flag).
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..errors import McpError, McpTimeoutError
from ..version import __version__
from .transport import DEFAULT_TIMEOUT, StdioTransport, Transport

#: The MCP protocol version this client speaks, sent in ``initialize``.
#: https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
PROTOCOL_VERSION = "2025-06-18"

#: How many times a crashed server is respawned before the client gives up. The
#: count resets on any clean call, so a server that recovers is not permanently
#: capped; a server that crashes on every call hits the cap and then fails fast.
MAX_RESPAWNS = 3
#: Base delay for the exponential backoff between respawns (0.5, 1.0, 2.0 s), so a
#: crash loop cannot hammer the process table.
RESPAWN_BASE_DELAY = 0.5


def _render_block(block: dict[str, Any]) -> str:
    """One MCP content block rendered as text for the model.

    A text block is its text. A non-text block (an image, an embedded resource)
    becomes a described placeholder rather than being dropped, so the model sees
    that something came back and what kind, instead of a silently empty result.
    """
    if block.get("text") is not None:
        return block["text"]
    kind = block.get("type") or "content"
    if kind == "image":
        return f"[image: {block.get('mimeType') or 'unknown type'}]"
    if kind == "resource":
        uri = (block.get("resource") or {}).get("uri") or "unknown"
        return f"[resource: {uri}]"
    return f"[{kind}]"


class Client:
    """A live connection to one MCP server, protocol over an injected transport."""

    def __init__(self, transport: Transport, *,
                 timeout: float = DEFAULT_TIMEOUT,
                 respawn_factory: Callable[[], Transport] | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self._transport = transport
        self._timeout = timeout
        #: Rebuilds a fresh transport after a crash, or ``None`` for a client
        #: over an injected transport (a test), which cannot respawn.
        self._respawn_factory = respawn_factory
        self._sleep = sleep or time.sleep
        self._respawns = 0
        self._id = 0
        self.server_info: dict[str, Any] | None = None
        self._handshake()
        self.tools: list[dict[str, Any]] = self._fetch_tools()

    @classmethod
    def spawn(cls, command: str, args: tuple[str, ...] | list[str] = (),
              env: dict[str, str] | None = None, *,
              timeout: float = DEFAULT_TIMEOUT,
              inherit_env: bool = True,
              sleep: Callable[[float], None] | None = None) -> "Client":
        """Spawn a server over stdio and return a connected client.

        The host layer's factory. A nonexistent command raises
        ``FileNotFoundError`` at spawn time. The spawn config is kept so a crashed
        server can be respawned mid-session; ``sleep`` is injectable for the
        backoff so the behavior is testable offline.
        """
        def factory() -> Transport:
            return StdioTransport(
                command,
                args=args,
                env=env,
                inherit_env=inherit_env,
            )
        return cls(factory(), timeout=timeout, respawn_factory=factory, sleep=sleep)

    # -- public calls ------------------------------------------------------

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None
                  ) -> dict[str, Any]:
        """Call a tool. Returns ``{"text": str, "error": bool}``.

        Content blocks' ``text`` fields are joined by newlines. A tool-level
        failure (``isError``) is data, not an exception, so the agent loop can
        keep going. A transport or protocol failure (crash, timeout, JSON-RPC
        error) does raise, so it surfaces as an ``ERROR`` tool result rather than
        a wrong answer.
        """
        params = {"name": str(name), "arguments": arguments or {}}
        try:
            response = self._request("tools/call", params)
        except McpError:
            # A crash closes the transport. If this client owns its process and
            # has respawns left, bring the server back and retry once, so a
            # mid-session crash does not permanently lose the server's tools.
            if not (self._transport.closed and self._can_respawn()):
                raise
            self._respawn()
            response = self._request("tools/call", params)
        result = response["result"]
        parts = [_render_block(block) for block in (result.get("content") or [])]
        # A clean call means the server is healthy again, so the respawn budget
        # resets; a server that never completes a call still hits the cap.
        self._respawns = 0
        return {"text": "\n".join(parts), "error": bool(result.get("isError"))}

    def close(self) -> None:
        """Close the transport (idempotent)."""
        self._transport.close()

    @property
    def closed(self) -> bool:
        return self._transport.closed

    # -- respawn -----------------------------------------------------------

    def _can_respawn(self) -> bool:
        return self._respawn_factory is not None and self._respawns < MAX_RESPAWNS

    def _respawn(self) -> None:
        """Rebuild the server after a crash, with backoff, and re-handshake.

        The registered tools call back into this same client, so a respawn is
        transparent to the registry: the new transport and freshly discovered
        tools replace the dead ones in place.
        """
        self._respawns += 1
        self._sleep(RESPAWN_BASE_DELAY * (2 ** (self._respawns - 1)))
        try:
            self._transport.close()
        except Exception:
            pass
        assert self._respawn_factory is not None  # guarded by _can_respawn
        self._transport = self._respawn_factory()
        self._id = 0
        self._handshake()
        self.tools = self._fetch_tools()

    # -- handshake and discovery -------------------------------------------

    def _handshake(self) -> None:
        response = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "boukensha", "version": __version__},
        })
        self.server_info = (response["result"] or {}).get("serverInfo")
        self._transport.notify(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _fetch_tools(self) -> list[dict[str, Any]]:
        response = self._request("tools/list")
        return (response["result"] or {}).get("tools") or []

    # -- JSON-RPC ----------------------------------------------------------

    def _request(self, method: str, params: dict[str, Any] | None = None
                 ) -> dict[str, Any]:
        """Send one request, return its response, raising on any JSON-RPC error.

        The single choke point for correctness: it applies the timeout, and it
        rejects an ``error`` response (or a response carrying neither ``result``
        nor ``error``) by raising instead of degrading to an empty result. On
        timeout it fires a best-effort ``notifications/cancelled`` so a
        well-behaved server can stop the abandoned work.
        """
        self._id += 1
        request_id = self._id
        message = {"jsonrpc": "2.0", "id": request_id,
                   "method": method, "params": params or {}}
        try:
            response = self._transport.request(message, request_id, self._timeout)
        except McpTimeoutError:
            self._notify_cancelled(request_id)
            raise

        if "error" in response and response["error"] is not None:
            error = response["error"]
            code = error.get("code") if isinstance(error, dict) else None
            detail = error.get("message") if isinstance(error, dict) else error
            raise McpError(f"MCP '{method}' failed: {detail} (code {code})")
        if response.get("result") is None:
            raise McpError(f"MCP '{method}' returned no result: {response!r}")
        return response

    def _notify_cancelled(self, request_id: int) -> None:
        """Best-effort: tell the server we abandoned a request. Never raises."""
        try:
            self._transport.notify({
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": request_id, "reason": "timeout"},
            })
        except McpError:
            pass

    def __str__(self) -> str:
        name = (self.server_info or {}).get("name", "?")
        return f"<Client server={name} tools={[t['name'] for t in self.tools]}>"

    __repr__ = __str__
