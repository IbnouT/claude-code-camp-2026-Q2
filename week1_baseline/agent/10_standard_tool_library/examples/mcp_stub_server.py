#!/usr/bin/env python3
"""A minimal, generic MCP server over stdio, for offline assertions.

It speaks just enough of the MCP 2025-06-18 protocol to exercise the client and
host layer with no network and no key: ``initialize``, the
``notifications/initialized`` notification, ``tools/list``, and ``tools/call``.
Message shapes follow the specification
(https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

Tools advertised by default:
- ``say``: a required ``message`` and an optional ``volume`` with an ``enum``.
  Echoes its arguments back so a caller can verify the round trip.
- ``boom``: always returns ``isError: true`` (a tool-level failure is data).

Env vars drive the deterministic failure/shape modes the assertions need, so the
default advertisement stays exactly ``say``/``boom`` with a two-string schema:
- ``STUB_EXTRA_TOOL``: advertise a second tool by that name (force a collision).
- ``STUB_ARRAY_PARAM``: give ``say`` an optional ``targets`` array parameter with
  an ``items`` schema, to prove structured schemas survive translation.
- ``STUB_INIT_ERROR``: answer ``initialize`` with a JSON-RPC error.
- ``STUB_SLEEP_SECONDS``: advertise a ``nap`` tool that sleeps that long before
  replying, to trip a short client timeout (the server stays alive).
- ``STUB_CRASH_ON``: exit the process when that tool is called, to prove a
  mid-call crash surfaces as an exit-code-aware error.
"""

import json
import os
import pathlib
import sys
import time

SERVER_INFO = {"name": "stub-mud", "version": "0.1.0"}


def _say_schema() -> dict:
    props = {
        "message": {"type": "string", "description": "what to say"},
        "volume": {
            "type": "string",
            "description": "how loud",
            "enum": ["whisper", "normal", "shout"],
        },
    }
    if os.environ.get("STUB_ARRAY_PARAM"):
        props["targets"] = {
            "type": "array",
            "description": "who to address",
            "items": {"type": "string"},
        }
    return {"type": "object", "properties": props, "required": ["message"]}


def _tools() -> list:
    tools = [
        {"name": "say", "description": "Speak a line into the room.",
         "inputSchema": _say_schema()},
        {"name": "boom", "description": "Always fails, to exercise the error path.",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    if os.environ.get("STUB_SLEEP_SECONDS"):
        tools.append({
            "name": "nap", "description": "Sleep, then reply (for timeout tests).",
            "inputSchema": {"type": "object", "properties": {}},
        })
    if os.environ.get("STUB_NONTEXT"):
        tools.append({
            "name": "picture", "description": "Return a non-text (image) result.",
            "inputSchema": {"type": "object", "properties": {}},
        })
    extra = os.environ.get("STUB_EXTRA_TOOL")
    if extra:
        tools.append({
            "name": extra, "description": "an extra tool, for collision tests",
            "inputSchema": {"type": "object", "properties": {}},
        })
    return tools


def _call(name: str, arguments: dict) -> dict:
    crash_once = os.environ.get("STUB_CRASH_ONCE")
    if crash_once:
        # Crash on the first tool call across all spawns (marker absent), then
        # serve normally, so a respawn recovers. The marker persists between the
        # crashed process and the one the client respawns.
        marker = pathlib.Path(crash_once)
        if not marker.exists():
            marker.write_text("crashed")
            sys.exit(1)
    crash_on = os.environ.get("STUB_CRASH_ON")
    if crash_on and name == crash_on:
        sys.exit(1)  # a mid-call crash: the pipe closes with a nonzero exit.
    if name == "nap":
        time.sleep(float(os.environ.get("STUB_SLEEP_SECONDS") or 0))
        return {"content": [{"type": "text", "text": "slept"}], "isError": False}
    if name == "picture":
        return {"content": [{"type": "image", "mimeType": "image/png",
                             "data": "iVBORw0KG"}], "isError": False}
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
    if method and method.startswith("notifications/"):
        return None  # notifications get no response.
    if method == "initialize":
        if os.environ.get("STUB_INIT_ERROR"):
            return {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32002, "message": "initialize refused"}}
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
