"""The MCP host layer: point boukensha at an MCP server and its tools become
boukensha tools.

Stateless module-level functions: the client and registry are passed in, so
this namespace owns nothing.

    from boukensha.tools import mcp
    client = mcp.register(registry, "mud-manager", args=["--mcp"],
                          env={"MUD_HOST": "localhost"}, prefix="tbamud")

``prefix`` scopes the discovered names agent-side (``tbamud`` -> ``tbamud__look``).
It is config policy applied here and never put on the wire: the server always
sees its own bare name.
"""

from __future__ import annotations

import atexit
from typing import Any

from ..errors import McpToolCollisionError
from ..mcp import Client
from ..mcp.transport import DEFAULT_TIMEOUT
from ..registry import Registry
from ..tool import Tool
from ..tool_result import ResultMode, render_tool_result

#: Joins a prefix to a tool name agent-side.
SEPARATOR = "__"


def register(registry: Registry, command: str,
             args: tuple[str, ...] | list[str] = (),
             env: dict[str, str] | None = None,
             prefix: str | None = None,
             timeout: float = DEFAULT_TIMEOUT,
             allow: list[str] | None = None,
             deny: tuple[str, ...] | list[str] = (),
             result_mode: ResultMode = "full") -> Client:
    """Spawn a server, register its tools, and return the client.

    ``timeout`` is the per-call ceiling handed to the client, so one hung tool
    call on this server cannot hang the agent turn. ``allow``/``deny`` scope which
    of the server's tools are registered (see :func:`register_client`). An
    ``atexit`` hook closes the client on process exit so the subprocess is reaped
    cleanly.
    """
    client = Client.spawn(command, args=args, env=env, timeout=timeout)
    atexit.register(_safe_close, client)
    register_client(
        registry,
        client,
        prefix=prefix,
        allow=allow,
        deny=deny,
        result_mode=result_mode,
    )
    return client


def register_client(registry: Registry, client: Client,
                    prefix: str | None = None,
                    allow: list[str] | None = None,
                    deny: tuple[str, ...] | list[str] = (),
                    result_mode: ResultMode = "full") -> int:
    """Register an already-spawned client's tools. Returns the registered count.

    Each discovered tool becomes a :class:`Tool` whose handler calls back into
    the client with the bare (remote) name. A tool-name collision, agent-side,
    raises before anything is registered for that tool.

    ``allow`` (when given) is the only tool names admitted; ``deny`` names tools
    to exclude. Both match the server's own (bare) names, so a permission policy
    reads the same whatever prefix the tools take agent-side. This is how a
    read-only or otherwise constrained variant is expressed as config, not code.
    """
    allowed = set(allow) if allow is not None else None
    denied = set(deny or ())
    taken = set(registry.tools)
    registered = 0
    for spec in client.tools:
        remote = spec["name"]
        if allowed is not None and remote not in allowed:
            continue
        if remote in denied:
            continue
        local = prefixed(remote, prefix)

        if local in taken:
            raise McpToolCollisionError(
                f"boukensha: MCP tool name collision on '{local}' — a tool by "
                f"that name is already registered. Give this server a distinct "
                f"`prefix:` in mcp_servers."
            )
        taken.add(local)

        registry.register(
            _build_tool(client, spec, local, remote, result_mode=result_mode)
        )
        registered += 1
    return registered


def prefixed(name: str, prefix: str | None) -> str:
    """``prefix + "__" + name`` for a non-blank prefix, else the bare name."""
    scope = (prefix or "").strip()
    return f"{scope}{SEPARATOR}{name}" if scope else name


def to_boukensha_params(input_schema: dict[str, Any] | None) -> dict[str, Any]:
    """Convert an MCP ``inputSchema`` into boukensha's ``parameters`` shape.

    Each property keeps its full JSON Schema fragment, not just ``type`` and
    ``description``: an array's ``items``, an object's nested ``properties``, a
    ``format`` or bounds all survive, so a structured parameter reaches the model
    intact instead of being flattened to a bare string. A missing ``type``
    defaults to ``"string"``. An ``enum`` stays a real schema key (backends pass
    it straight to the wire, so every provider enforces it) and is also appended
    to the description, belt-and-suspenders for models that weight prose over the
    strict schema.
    """
    props = (input_schema or {}).get("properties") or {}
    params: dict[str, Any] = {}
    for pname, raw in props.items():
        schema = dict(raw or {})
        schema.setdefault("type", "string")
        desc = str(schema.get("description") or "")
        enum = schema.get("enum")
        if enum:
            joined = ", ".join(str(v) for v in enum)
            desc = f"{desc} (one of: {joined})".strip()
        schema["description"] = desc
        params[pname] = schema
    return params


# -- internals -------------------------------------------------------------


#: Cap on a tool result's text handed back to the model. An MCP tool result
#: becomes a permanent tool_result message, so an unbounded one (a long room
#: description, a big file read) inflates every later turn's tokens and cost.
#: Truncation is announced in the text, so the model knows the data was cut.
MAX_RESULT_CHARS = 8000


def _build_tool(client: Client, spec: dict[str, Any],
                local: str, remote: str, *,
                result_mode: ResultMode = "full") -> Tool:
    """Build the boukensha Tool for one discovered MCP tool.

    The handler is ``**kwargs`` and forwards to the client under the bare
    ``remote`` name captured here, so the server sees its own name even when the
    agent-side name is prefixed. Only ``inputSchema.required`` members are marked
    required in the wire schema.
    """
    params = to_boukensha_params(spec.get("inputSchema"))
    declared_required = set((spec.get("inputSchema") or {}).get("required") or [])
    required = frozenset(declared_required & set(params))

    def handler(**kwargs: Any) -> str:
        result = client.call_tool(remote, {str(k): v for k, v in kwargs.items()})
        text = render_tool_result(result["text"], result_mode)
        if len(text) > MAX_RESULT_CHARS:
            dropped = len(text) - MAX_RESULT_CHARS
            text = text[:MAX_RESULT_CHARS] + f"\n...[truncated {dropped} chars]"
        return f"error: {text}" if result["error"] else text

    return Tool(
        name=local,
        description=str(spec.get("description") or ""),
        parameters=params,
        handler=handler,
        required=required,
    )


def _safe_close(client: Client) -> None:
    try:
        client.close()
    except Exception:
        pass
