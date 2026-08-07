"""Profiled, generated MCP surface for the mortal gateway.

    python -m mud_gateway.mcp_server --prove
    python -m mud_gateway.mcp_server --measure
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any, Callable

from .commands import BY_NAME, IMMORTAL, Capability
from . import identity, recall, rules
from .journal import Journal
from .knowledge import KnowledgeStore
from .knowledge_projection import KnowledgeProjector
from .navigation import NavigationExecutor
from .navigation.graph import WorldGraph
from .state_block import render_state_block
from .campaign import mission_readiness, readiness_text
from .economy import Economy, report_text as economy_report_text
from .state_notes import record_service, record_state_fields
from .survival import Survival
from .profiles import (
    PROFILES,
    CapabilityUnavailable,
    Invocation,
    PermissionDenied,
    Surface,
    load_profile,
)
from .raw import Role, send_raw
from .reset_control import ResetControlServer, ResetCoordinator
from .results import CommandFailure, CommandObservation
from .session import ReconnectFailed, Session
from .settings import GatewaySettings
from .wire import NotConnected


async def seed_login_observations(session: Session, journal: Journal) -> None:
    """Capture the initial room and player state without invoking a model."""

    for command, reason in (
        ("look", "login_room_state"),
        ("score", "login_player_state"),
    ):
        trace_id = uuid.uuid4().hex
        journal.append(
            session.id,
            "observer_probe",
            {"command": command, "reason": reason},
            trace_id=trace_id,
        )
        await session.command(command, trace_id=trace_id)


async def execute(
        session: Session | None,
        invocation: Invocation,
        surface: Surface,
        *,
        journal: Journal,
        event_session: str,
        navigation: NavigationExecutor | None = None,
        state_reader: Callable[[], str] | None = None,
        state_notes: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        service_notes: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        economy: Economy | None = None,
        knowledge_reader: Any = None,
        recall_reader: Callable[[str, Any], str] | None = None,
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
        if capability.execution == "routine":
            if capability.name == "mission_readiness":
                if knowledge_reader is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the campaign capability")
                report = mission_readiness(
                    knowledge_reader, invocation.arguments["target"]
                )
                event = journal.append(
                    event_session, "mission_readiness", report,
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=readiness_text(report),
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if capability.name == "note_service":
                if service_notes is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the knowledge capability")
                recorded = service_notes(invocation.arguments)
                event = journal.append(
                    event_session, "service_note", recorded,
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=json.dumps(recorded, separators=(",", ":"),
                                    sort_keys=True),
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if capability.name == "bank_surplus":
                if economy is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the economy capability")
                recorded = await economy.bank_surplus()
                event = journal.append(
                    event_session, "tool_result",
                    {
                        "tool": invocation.tool,
                        "capability": capability.name,
                        "complete": True,
                        "sequence": journal.last_seq(event_session),
                    },
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=economy_report_text(recorded),
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if capability.name == "note_state":
                if state_notes is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the knowledge capability")
                recorded = state_notes(invocation.arguments)
                text = json.dumps(recorded, separators=(",", ":"),
                                  sort_keys=True)
                event = journal.append(
                    event_session,
                    "state_fields",
                    recorded,
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=text,
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if capability.name == "recall":
                if recall_reader is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the knowledge capability")
                text = recall_reader(
                    str(invocation.arguments.get("about") or ""),
                    invocation.arguments.get("name"),
                )
                event = journal.append(
                    event_session,
                    "tool_result",
                    {
                        "tool": invocation.tool,
                        "capability": capability.name,
                        "complete": True,
                    },
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=text,
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if capability.name == "recall_state":
                if state_reader is None:
                    raise CapabilityUnavailable(
                        f"{capability.name!r} needs the knowledge capability")
                text = state_reader()
                event = journal.append(
                    event_session,
                    "tool_result",
                    {
                        "tool": invocation.tool,
                        "capability": capability.name,
                        "complete": True,
                        "sequence": journal.last_seq(event_session),
                    },
                    trace_id=trace_id,
                )
                return CommandObservation(
                    tool=invocation.tool,
                    capability=capability.name,
                    family=capability.family,
                    command=None,
                    text=text,
                    complete=True,
                    sequence=event.seq,
                    trace_id=trace_id,
                )
            if navigation is None:
                raise CapabilityUnavailable(
                    f"{capability.name!r} needs the navigation capability")
            if capability.name == "sweep":
                report = await navigation.sweep()
            elif capability.name == "travel_to":
                report = await navigation.travel(
                    invocation.arguments["destination"]
                )
            else:
                raise CapabilityUnavailable(
                    f"{capability.name!r} has no routine implementation")
            journal.append(
                event_session,
                "tool_result",
                {
                    "tool": invocation.tool,
                    "capability": capability.name,
                    "complete": True,
                    "sequence": journal.last_seq(event_session),
                },
                trace_id=trace_id,
            )
            return CommandObservation(
                tool=invocation.tool,
                capability=capability.name,
                family=capability.family,
                command=None,
                text=report.text(),
                complete=True,
                sequence=journal.last_seq(event_session),
                trace_id=trace_id,
            )
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
    elif isinstance(error, ReconnectFailed):
        code = "reconnect_failed"
    elif isinstance(error, NotConnected):
        code = "connection_lost"
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
    journal = Journal(settings.journal, exclusive=bool(settings.session_id))
    run_id = settings.gateway_session_id or f"mcp-{uuid.uuid4().hex[:12]}"
    record_profile(journal, run_id, surface)
    session: Session | None = None
    control: ResetControlServer | None = None
    knowledge_store: KnowledgeStore | None = None
    navigation: NavigationExecutor | None = None
    state_reader: Callable[[], str] | None = None
    state_notes: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    service_notes: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    economy: Economy | None = None
    knowledge_reader: Any = None
    recall_reader: Callable[[str, Any], str] | None = None

    async def game_session() -> Session:
        nonlocal economy, knowledge_reader, knowledge_store, navigation, recall_reader, service_notes, session, state_notes, state_reader
        if session is None:
            profile = settings.player(player_profile)
            password = settings.player_password(profile.id)
            if not password:
                raise RuntimeError(
                    f"{profile.password_env} is required for player profile "
                    f"{profile.id!r}"
                )
            knowledge_store = KnowledgeStore(
                settings.config_dir / "profiles" / profile.id / "knowledge.db",
                player_id=profile.id,
            )
            session = Session(
                journal,
                name=profile.character,
                password=password,
                host=settings.host,
                port=settings.port,
                session_id=settings.gateway_session_id,
                knowledge=KnowledgeProjector(
                    knowledge_store,
                    player_id=profile.id,
                ),
            )
            record_profile(journal, session.id, surface)
            if settings.capabilities.get("knowledge") and knowledge_store:
                # Record what earlier runs saw as one map. The map the
                # agent walks is computed live, so a failure here costs a
                # report rather than the run.
                try:
                    bound = identity.record(
                        knowledge_store,
                        knowledge_store.current_facts(layer="learned"),
                    )
                    payload = {
                        "phase": "start",
                        "places": len(bound),
                        "rooms": len(set(bound.values())),
                    }
                except Exception as error:
                    payload = {"phase": "start", "failed": str(error)}
                journal.append(session.id, "identity", payload)
            await session.open()
            await seed_login_observations(session, journal)
            survival = None
            if settings.capabilities.get("survival") and knowledge_store:
                survival = Survival(
                    session,
                    knowledge_store,
                    settings.capability_settings.get("survival"),
                )
            if settings.capabilities.get("navigation") and knowledge_store:
                navigation = NavigationExecutor(
                    session,
                    knowledge_store,
                    settings.capability_settings.get("navigation"),
                    reflexes=survival,
                )
            if survival is not None:
                await survival.apply_wimpy()
            if settings.capabilities.get("knowledge") and knowledge_store:
                store = knowledge_store
                live = session
                # Advice the agent reads every turn. A rule it never sees
                # is a rule it does not have.
                advice = rules.render(
                    rules.load(settings.rules_file),
                    settings.capability_settings.get("knowledge", {}),
                )

                def read_state() -> str:
                    return render_state_block(
                        store,
                        live.observations,
                        live.observations.knowledge,
                        advice=advice,
                        player_id=profile.id,
                    )

                state_reader = read_state

                def read_knowledge(about: str, name: Any = None) -> str:
                    return recall.answer(
                        store,
                        WorldGraph.from_store(store),
                        about,
                        place_id=live.observations.knowledge.current_place_id,
                        name=None if name is None else str(name),
                        player_id=profile.id,
                    )

                recall_reader = read_knowledge

                def write_notes(arguments: dict[str, Any]) -> dict[str, Any]:
                    return record_state_fields(
                        store,
                        live.observations.knowledge,
                        live.id,
                        live.journal.last_seq(live.id),
                        perceive=arguments.get("perceive"),
                        threat=arguments.get("threat"),
                        learned=arguments.get("learned"),
                    )

                state_notes = write_notes

                def write_service(arguments: dict[str, Any]) -> dict[str, Any]:
                    return record_service(
                        store,
                        live.observations.knowledge,
                        live.id,
                        live.journal.last_seq(live.id),
                        kind=arguments["kind"],
                        detail=arguments.get("detail"),
                    )

                service_notes = write_service
            if settings.capabilities.get("campaign") and knowledge_store:
                knowledge_reader = knowledge_store
            if settings.capabilities.get("economy") and knowledge_store:
                economy = Economy(
                    session,
                    knowledge_store,
                    navigation,
                    settings.capability_settings.get("economy"),
                )
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
                navigation=navigation,
                state_reader=state_reader,
                recall_reader=recall_reader,
                state_notes=state_notes,
                service_notes=service_notes,
                economy=economy,
                knowledge_reader=knowledge_reader,
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
        if settings.control_socket is not None and settings.session_dir is not None:
            await game_session()
            coordinator = ResetCoordinator(
                settings,
                session=lambda: session,
                knowledge=knowledge_store,
            )
            control = ResetControlServer(
                settings.control_socket,
                settings.session_dir / "control.token",
                coordinator,
            )
            await control.start()
        async with stdio_server() as (read, write):
            await server.run(
                read,
                write,
                server.create_initialization_options(),
            )
    finally:
        if control is not None:
            await control.close()
        if session is not None:
            await session.close()
        if knowledge_store is not None:
            if settings.capabilities.get("knowledge"):
                # Fold what this run saw into the joined map, so the next
                # run starts from one map instead of re-learning ground.
                try:
                    identity.record(
                        knowledge_store,
                        knowledge_store.current_facts(layer="learned"),
                    )
                except Exception as error:
                    journal.append(
                        "gateway",
                        "identity",
                        {"phase": "end", "failed": str(error)},
                    )
            knowledge_store.close()
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
    extensions = frozenset().union(
        frozenset({"sweep", "travel_to"})
        if settings.capabilities.get("navigation") else frozenset(),
        frozenset({"recall", "recall_state", "note_state", "note_service"})
        if settings.capabilities.get("knowledge") else frozenset(),
        frozenset({"bank_surplus"})
        if settings.capabilities.get("economy") else frozenset(),
        frozenset({"mission_readiness"})
        if settings.capabilities.get("campaign") else frozenset(),
    )
    surface = Surface(profile, extensions)
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
