#!/usr/bin/env python3
"""A minimal, generic MCP server over stdio, for offline assertions.

It speaks just enough of the MCP 2025-06-18 protocol to exercise the client and
host layer with no network and no key: ``initialize``, the
``notifications/initialized`` notification, ``tools/list``, and ``tools/call``.
Message shapes follow the specification
(https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

Tools advertised:
- ``say``: a required ``message`` and an optional ``volume`` with an ``enum``.
  Echoes its arguments back so a caller can verify the round trip.
- ``boom``: always returns ``isError: true`` (a tool-level failure is data).

An env var ``STUB_EXTRA_TOOL`` adds a second tool by that name, so a test can
force a name collision between two servers.
"""

import json
import os
import sys

SERVER_INFO = {"name": "stub-mud", "version": "0.1.0"}

TOOLS = [
    {
        "name": "say",
        "description": "Speak a line into the room.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "what to say"},
                "volume": {
                    "type": "string",
                    "description": "how loud",
                    "enum": ["whisper", "normal", "shout"],
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "boom",
        "description": "Always fails, to exercise the error path.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _tools() -> list:
    tools = list(TOOLS)
    extra = os.environ.get("STUB_EXTRA_TOOL")
    if extra:
        tools.append({
            "name": extra,
            "description": "an extra tool, for collision tests",
            "inputSchema": {"type": "object", "properties": {}},
        })
    return tools


def _call(name: str, arguments: dict) -> dict:
    if name == "boom":
        return {"content": [{"type": "text", "text": "kaboom"}], "isError": True}
    if name == "say":
        message = arguments.get("message", "")
        volume = arguments.get("volume", "normal")
        return {
            "content": [{"type": "text", "text": f"[{volume}] you say: {message}"}],
            "isError": False,
        }
    # An unknown extra tool just echoes its name.
    return {"content": [{"type": "text", "text": f"ran {name}"}], "isError": False}


def _handle(msg: dict):
    method = msg.get("method")
    if method == "notifications/initialized":
        return None
    result = None
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "tools/list":
        result = {"tools": _tools()}
    elif method == "tools/call":
        params = msg.get("params") or {}
        result = _call(params.get("name", ""), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": msg.get("id"),
                "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        response = _handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
