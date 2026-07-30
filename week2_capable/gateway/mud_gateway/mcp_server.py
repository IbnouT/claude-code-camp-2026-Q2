"""Profiled, generated MCP surface for the mortal gateway.

    python -m mud_gateway.mcp_server --prove
    python -m mud_gateway.mcp_server --measure
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from .commands import BY_NAME, IMMORTAL, Capability
from .journal import Journal
from .profiles import (
    PROFILES,
    CapabilityUnavailable,
    Invocation,
    PermissionDenied,
    Surface,
    load_profile,
)
from .raw import Role, send_raw
from .results import CommandFailure, CommandObservation
from .session import Session
from .settings import GatewaySettings


async def execute(
        session: Session | None,
        invocation: Invocation,
        surface: Surface,
        *,
        journal: Journal,
        event_session: str,
) -> CommandObservation:
    """Execute one authorized capability and trace it end to end."""
    capability = invocation.capability
    trace_id = uuid.uuid4().hex
    journal.append(
        event_session,
        "tool_call",
        {
            "tool": invocation.tool,
            "capability": capability.name,
            "profile_id": surface.profile.id,
        },
        trace_id=trace_id,
    )

    command: str | None
    if capability.execution == "status":
        connected = bool(session and session.logged_in)
        event = journal.append(
            event_session,
            "status",
            {"connected": connected},
            trace_id=trace_id,
        )
        text = json.dumps({"connected": connected}, separators=(",", ":"))
        complete = True
        sequence = event.seq
        command = None
    else:
        if session is None:
            raise RuntimeError(f"{capability.name} requires a game session")
        if capability.execution == "wire":
            command = capability.build(invocation.arguments)
            reply = await session.command(command, trace_id=trace_id)
        elif capability.execution == "poll":
            command = None
            reply = await session.poll(trace_id=trace_id)
        elif capability.execution == "raw":
            command = invocation.arguments["line"]
            reply = await send_raw(
                session,
                command,
                role=Role.PROFILE,
                reason=invocation.arguments["reason"],
                trace_id=trace_id,
            )
        else:
            raise CapabilityUnavailable(
                f"{capability.name!r} has no runtime implementation")
        text = reply.text
        complete = reply.complete
        sequence = reply.seq

    journal.append(
        event_session,
        "tool_result",
        {
            "tool": invocation.tool,
            "capability": capability.name,
            "complete": complete,
            "sequence": sequence,
        },
        trace_id=trace_id,
    )
    return CommandObservation(
        tool=invocation.tool,
        capability=capability.name,
        family=capability.family,
        command=command,
        text=text,
        complete=complete,
        sequence=sequence,
        trace_id=trace_id,
    )


def failure(
        tool: str,
        error: Exception,
        surface: Surface,
        *,
        journal: Journal | None = None,
        event_session: str | None = None,
) -> CommandFailure:
    """Convert and optionally record a rejected tool call."""
    capability_name = (
        error.capability if isinstance(error, PermissionDenied)
        else tool if tool in BY_NAME else None
    )
    capability = BY_NAME.get(capability_name or "")
    if isinstance(error, PermissionDenied):
        code = "permission_denied"
    elif isinstance(error, CapabilityUnavailable):
        code = "capability_unavailable"
    elif isinstance(error, ValueError):
        code = "invalid_arguments"
    else:
        code = "command_failed"
    result = CommandFailure(
        tool=tool,
        capability=capability_name,
        family=capability.family if capability else None,
        code=code,
        message=str(error),
    )
    if journal is not None and event_session is not None:
        journal.append(
            event_session,
            "tool_rejected",
            {
                "tool": tool,
                "capability": capability_name,
                "profile_id": surface.profile.id,
                "code": code,
                "message": str(error),
            },
        )
    return result


def record_profile(
        journal: Journal,
        event_session: str,
        surface: Surface,
) -> None:
    journal.append(event_session, "surface_profile", surface.measurement())


def prove(surface: Surface) -> int:
    """Print and verify the configured agent surface."""
    advertised = surface.schemas()
    names = sorted(schema["name"] for schema in advertised)
    measurement = surface.measurement()
    print(f"  profile          : {surface.profile.id}")
    print(f"  projection       : {surface.profile.projection}")
    print(f"  advertised tools : {len(advertised)}")
    print(f"  schema bytes     : {surface.schema_bytes:,}")
    print(f"  capability digest: {surface.profile.capability_digest}")
    print(f"  names            : {', '.join(names)}")

    failures: list[str] = []
    overlap = set(names) & IMMORTAL
    if overlap:
        failures.append(f"privileged names advertised: {sorted(overlap)}")

    for name in surface.profile.allowed:
        capability = BY_NAME[name]
        if capability.execution != "wire":
            continue
        try:
            line = capability.build(_example_arguments(capability))
        except Exception as error:
            failures.append(f"{name} cannot build its example: {error}")
            continue
        first = line.split()[0].lower() if line.split() else ""
        if first in IMMORTAL:
            failures.append(f"{name} builds a privileged line: {line!r}")

    if measurement["coverage"] > 1:
        failures.append("profile coverage exceeds the registry")
    for problem in failures:
        print(f"  FAIL: {problem}")
    print(f"\n  SURFACE PROOF: {'PASS' if not failures else 'FAIL'}")
    return 0 if not failures else 1


def measure() -> int:
    rows = [Surface(profile).measurement() for profile in PROFILES.values()]
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


async def serve(
    surface: Surface,
    settings: GatewaySettings,
    *,
    player_profile: str | None = None,
) -> None:
    """Run one session-static profile over MCP stdio."""
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    server = Server("torii")
    journal = Journal(settings.journal)
    run_id = f"mcp-{uuid.uuid4().hex[:12]}"
    record_profile(journal, run_id, surface)
    session: Session | None = None

    async def game_session() -> Session:
        nonlocal session
        if session is None:
            profile = settings.player(player_profile)
            password = settings.player_password(profile.id)
            if not password:
                raise RuntimeError(
                    f"{profile.password_env} is required for player profile "
                    f"{profile.id!r}"
                )
            session = Session(
                journal,
                name=profile.character,
                password=password,
                host=settings.host,
                port=settings.port,
            )
            record_profile(journal, session.id, surface)
            await session.open()
        return session

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(**schema) for schema in surface.schemas()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            invocation = surface.resolve(name, arguments)
            target = (
                session if invocation.capability.execution == "status"
                else await game_session()
            )
            result = await execute(
                target,
                invocation,
                surface,
                journal=journal,
                event_session=target.id if target is not None else run_id,
            )
        except Exception as error:
            result = failure(
                name,
                error,
                surface,
                journal=journal,
                event_session=session.id if session is not None else run_id,
            )
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=result.model_dump_json())
            ],
            isError=isinstance(result, CommandFailure),
        )

    try:
        async with stdio_server() as (read, write):
            await server.run(
                read,
                write,
                server.create_initialization_options(),
            )
    finally:
        if session is not None:
            await session.close()
        journal.close()


def main(argv: list[str] | None = None) -> int:
    settings = GatewaySettings.load()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--player-profile",
        choices=sorted(settings.players),
        help="configured player identity for this MCP session",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        help="session-static named profile",
    )
    parser.add_argument(
        "--allow",
        help="comma-separated capability allowlist for this session",
    )
    parser.add_argument(
        "--prove",
        action="store_true",
        help="verify and print the configured surface",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="print schema and coverage measurements for named profiles",
    )
    args = parser.parse_args(argv)
    if args.measure:
        return measure()
    if args.profile is None and args.allow is None:
        profile = settings.effective_profile()
    else:
        allow = None if args.allow is None else (
            name.strip() for name in args.allow.split(",") if name.strip()
        )
        profile = load_profile(args.profile or settings.profile, allow)
    surface = Surface(profile)
    if args.prove:
        return prove(surface)
    import asyncio
    asyncio.run(serve(surface, settings, player_profile=args.player_profile))
    return 0


def _example_arguments(capability: Capability) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for argument in capability.arguments:
        if argument.default is not None:
            result[argument.name] = argument.default
        elif argument.required and argument.choices:
            result[argument.name] = argument.choices[0]
        elif argument.kind == "integer":
            result[argument.name] = 1
        elif argument.required and argument.kind == "array":
            result[argument.name] = [argument.item_choices[0]]
        elif argument.required:
            result[argument.name] = "thing"
    return result


if __name__ == "__main__":
    sys.exit(main())
