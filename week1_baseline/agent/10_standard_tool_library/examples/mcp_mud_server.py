#!/usr/bin/env python3
"""A small MUD served as a real MCP server over stdio, a domain-shaped fixture.

Unlike ``mcp_stub_server.py`` (a bare protocol-conformance fixture), this is a
real, if tiny, game: ``look`` and ``move`` walk the same clearing/grove/brook/
cave world steps 07-08 use for their live demos, but exposed as MCP tools rather
than inline ``dsl.tool`` registrations. The test suite round-trips it through the
host (``tests/test_mcp_client.py``, ``TestDomainServer``), proving the host works
against a domain-shaped server and not only the generic stub. It needs no network
and no external daemon, so the repo can run it anywhere.
"""

import json
import sys

WORLD = {
    "clearing": ("A sunlit forest clearing. A path leads north and a stream runs east.",
                 {"north": "grove", "east": "brook"}),
    "grove": ("A mossy grove ringed with standing stones. North goes on, south returns.",
              {"north": "cave", "south": "clearing"}),
    "brook": ("A shallow brook. The only way is back west.", {"west": "clearing"}),
    "cave": ("A dark cave mouth. The way south returns to the grove.", {"south": "grove"}),
}

SERVER_INFO = {"name": "clearing-mud", "version": "0.1.0"}

TOOLS = [
    {
        "name": "look",
        "description": "Describe the current room and its exits.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "move",
        "description": "Move through an exit of the current room.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "which exit to take",
                    "enum": ["north", "south", "east", "west"],
                },
            },
            "required": ["direction"],
        },
    },
]

state = {"room": "clearing"}


def _describe(room: str) -> str:
    desc, exits = WORLD[room]
    return f"{desc} Exits: {', '.join(exits)}."


def _call(name: str, arguments: dict) -> dict:
    if name == "look":
        return {"content": [{"type": "text", "text": _describe(state["room"])}],
                "isError": False}
    if name == "move":
        direction = arguments.get("direction", "")
        _desc, exits = WORLD[state["room"]]
        if direction not in exits:
            return {"content": [{"type": "text",
                                 "text": f"You cannot go {direction} from here. "
                                         f"Exits: {', '.join(exits)}."}],
                    "isError": True}
        state["room"] = exits[direction]
        return {"content": [{"type": "text", "text": _describe(state["room"])}],
                "isError": False}
    return {"content": [{"type": "text", "text": f"unknown tool {name}"}],
            "isError": True}


def _handle(msg: dict):
    method = msg.get("method")
    if method and method.startswith("notifications/"):
        return None
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18",
                  "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    elif method == "tools/list":
        result = {"tools": TOOLS}
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
