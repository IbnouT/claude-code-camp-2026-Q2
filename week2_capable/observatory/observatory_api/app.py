"""Local read API and static host for the Boukensha observatory."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx
from mud_gateway.contracts import contract_schemas
from mud_gateway.stream import serialize_event
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route

from .capabilities import discover
from .contracts import (
    AskRequest,
    IncidentExportRequest,
    LiveControlRequest,
)
from .incidents import build_capsule
from .projections.history import diagnostic_history
from .projections.knowledge import project_knowledge
from .projections.live import project_live
from .projections.session import project_recorded_session
from .queries import answer, answer_operation
from .queries.model import ModelTranslator
from .settings import Settings
from .sources.benchmark import BenchmarkSource
from .sources.atlas import AtlasSource
from .sources.comparison import rendering_comparison
from .sources.gateway import GatewaySource
from .sources.runtime import RuntimeSource, RuntimeSourceError
from .sources.recorded_session import RecordedSessionSource


def create_app(
    settings: Settings | None = None,
    *,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
    copilot_transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    active = settings or Settings.from_environment()
    gateway = GatewaySource(
        active.gateway_url,
        transport=gateway_transport,
    )
    runtime = (
        None
        if active.runtime_root is None
        else RuntimeSource(active.runtime_root)
    )
    benchmark = (
        BenchmarkSource(active.benchmark_root)
        if active.benchmark_root is not None
        else None
    )
    recorded_sessions = (
        RecordedSessionSource(active.benchmark_root)
        if active.benchmark_root is not None
        else None
    )
    atlas = AtlasSource(active.world_root)
    model_spend = 0.0
    translator = (
        ModelTranslator(
            endpoint=active.copilot_endpoint,
            api_key=active.copilot_api_key,
            model=active.copilot_model,
            input_rate=active.copilot_input_rate,
            output_rate=active.copilot_output_rate,
            transport=copilot_transport,
        )
        if (
            active.copilot_model
            and active.copilot_api_key
            and active.copilot_spend_cap > 0
            and active.copilot_input_rate > 0
            and active.copilot_output_rate > 0
        )
        else None
    )

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "evidence_plane": "read_only",
                "control_plane": "authenticated_local",
            }
        )

    async def capabilities(_request: Request) -> JSONResponse:
        result = await discover(
            active,
            gateway_transport=gateway_transport,
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def sessions(_request: Request) -> JSONResponse:
        if runtime is not None and runtime.available:
            try:
                available = runtime.sessions()
            except RuntimeSourceError as error:
                return _runtime_error(error)
            players: dict[str, dict[str, str]] = {}
            for session in available:
                players.setdefault(
                    session.player_id,
                    {
                        "id": session.player_id,
                        "label": session.character,
                    },
                )
            return JSONResponse(
                {
                    "version": 1,
                    "players": list(players.values()),
                    "sessions": [session.public() for session in available],
                }
            )
        try:
            payload = await gateway.sessions()
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)
        fallback = [
            {
                "id": session,
                "player_id": "legacy",
                "character": "Legacy gateway",
                "gateway_session_id": session,
                "state": "unknown",
                "control_state": None,
                "control_available": False,
                "capture_status": "unknown",
                "created_at": "",
                "updated_at": "",
                "ended_at": None,
                "event_count": 0,
                "latest_seq": 0,
                "legacy": True,
                "live": True,
            }
            for session in payload["sessions"]
        ]
        return JSONResponse(
            {
                "version": 1,
                "players": [{"id": "legacy", "label": "Legacy gateway"}],
                "sessions": fallback,
            }
        )

    async def contracts(_request: Request) -> JSONResponse:
        if runtime is not None and runtime.available:
            return JSONResponse(contract_schemas())
        try:
            return JSONResponse(await gateway.json("/contracts"))
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

    async def gateway_events(request: Request) -> Response:
        session = request.path_params["session"]
        endpoint = request.path_params["endpoint"]
        if endpoint not in {"events", "replay"}:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if runtime is not None and runtime.available:
            try:
                selected = runtime.session(session)
            except RuntimeSourceError as error:
                return _runtime_error(error)
            if selected is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            return _runtime_events(request, runtime, selected.id, endpoint)
        query = list(request.query_params.multi_items())
        context = gateway.stream(
            f"/sessions/{session}/{endpoint}",
            query=query,
        )
        try:
            upstream = await context.__aenter__()
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

        async def body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await context.__aexit__(None, None, None)

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def live_snapshot(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        session_id = request.path_params["session"]
        try:
            selected = runtime.session(session_id)
            if selected is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            through_value = request.query_params.get("through")
            through = int(through_value) if through_value else None
            result = project_live(
                selected,
                runtime.events(session_id),
                runtime.agent_events(session_id),
                through=through,
            )
        except (RuntimeSourceError, ValueError) as error:
            return _runtime_error(error)
        return JSONResponse(result.model_dump(mode="json"))

    async def live_control(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        try:
            payload = LiveControlRequest.model_validate(await request.json())
            receipt = runtime.control(
                request.path_params["session"],
                request_id=payload.request_id,
                action=payload.action,
                instruction=payload.instruction,
                expected_sequence=payload.expected_sequence,
            )
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_control", "detail": str(error)},
                status_code=422,
            )
        except RuntimeSourceError as error:
            return JSONResponse(
                {"error": "control_rejected", "detail": str(error)},
                status_code=409,
            )
        return JSONResponse(receipt)

    async def runs(_request: Request) -> JSONResponse:
        available = () if benchmark is None else benchmark.runs()
        return JSONResponse(
            {"runs": [run.model_dump(mode="json") for run in available]}
        )

    async def recorded_session_catalog(_request: Request) -> JSONResponse:
        available = (
            ()
            if recorded_sessions is None
            else recorded_sessions.catalog()
        )
        return JSONResponse(
            {
                "sessions": [
                    item.model_dump(mode="json") for item in available
                ]
            }
        )

    async def recorded_session(request: Request) -> JSONResponse:
        if recorded_sessions is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        bundle = recorded_sessions.load(request.path_params["run_id"])
        if bundle is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        result = project_recorded_session(bundle)
        return JSONResponse(result.model_dump(mode="json"))

    async def investigation(request: Request) -> JSONResponse:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = benchmark.investigation(request.path_params["run_id"])
        if result is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(result.model_dump(mode="json"))

    async def knowledge(request: Request) -> JSONResponse:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = benchmark.investigation(request.path_params["run_id"])
        if result is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        projection = project_knowledge(result)
        return JSONResponse(projection.model_dump(mode="json"))

    async def history(_request: Request) -> JSONResponse:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = diagnostic_history(benchmark)
        return JSONResponse(result.model_dump(mode="json"))

    async def export_incident(request: Request) -> Response:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        try:
            payload = IncidentExportRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_incident", "detail": str(error)},
                status_code=422,
            )
        result = benchmark.investigation(payload.run_id)
        if result is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        capsule = build_capsule(
            payload,
            result,
            project_knowledge(result),
            diagnostic_history(benchmark),
            active.revision,
        )
        safe_name = "".join(
            character
            for character in result.run.journey.casefold()
            if character.isalnum() or character in {"-", "_"}
        )
        return Response(
            capsule.model_dump_json(),
            media_type="application/vnd.boukensha.incident+json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="boukensha-{safe_name}-incident.json"'
                ),
                "Cache-Control": "no-store",
            },
        )

    async def comparisons(_request: Request) -> JSONResponse:
        result = (
            None
            if active.benchmark_root is None
            else rendering_comparison(active.benchmark_root)
        )
        return JSONResponse(
            {
                "comparisons": []
                if result is None
                else [
                    {
                        "id": result.id,
                        "title": result.title,
                        "journey": result.journey,
                    }
                ]
            }
        )

    async def comparison(request: Request) -> JSONResponse:
        if active.benchmark_root is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = rendering_comparison(active.benchmark_root)
        if result is None or result.id != request.path_params["comparison_id"]:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(result.model_dump(mode="json"))

    async def world_atlas(request: Request) -> JSONResponse:
        level = request.query_params.get("level", "overview")
        if level not in {"overview", "zone"}:
            return JSONResponse(
                {"error": "invalid_level", "detail": "Use overview or zone"},
                status_code=422,
            )
        zone_value = request.query_params.get("zone")
        if level == "zone" and zone_value is None:
            return JSONResponse(
                {"error": "zone_required", "detail": "Zone detail needs zone"},
                status_code=422,
            )
        try:
            zone = int(zone_value) if zone_value is not None else None
        except ValueError:
            return JSONResponse(
                {"error": "invalid_zone", "detail": "Zone must be an integer"},
                status_code=422,
            )
        result = atlas.projection(level=level, zone=zone)
        return JSONResponse(result.model_dump(mode="json"))

    async def ask(request: Request) -> JSONResponse:
        nonlocal model_spend
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        try:
            payload = AskRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_query", "detail": str(error)},
                status_code=422,
            )
        result = answer(payload, benchmark, recorded_sessions)
        if (
            result.tier == "model_disabled"
            and payload.allow_model
            and translator is not None
        ):
            reserve = (
                1_000 * active.copilot_input_rate
                + 80 * active.copilot_output_rate
            ) / 1_000_000
            if model_spend + reserve <= active.copilot_spend_cap:
                try:
                    translation = await translator.translate(payload.question)
                    translated = answer_operation(
                        translation.operation,
                        payload,
                        benchmark,
                        recorded_sessions,
                    )
                    model_spend += translation.cost_usd
                    result = translated.model_copy(
                        update={
                            "tier": "model_translated",
                            "model_cost_usd": translation.cost_usd,
                        }
                    )
                except (httpx.HTTPError, ValueError):
                    pass
        return JSONResponse(result.model_dump(mode="json"))

    async def index(_request: Request) -> Response:
        target = active.web_dist / "index.html"
        if not target.exists():
            return JSONResponse(
                {
                    "error": "frontend_not_built",
                    "detail": "Run npm install and npm run build in web/",
                },
                status_code=503,
            )
        return FileResponse(target)

    async def asset(request: Request) -> Response:
        relative = Path(request.path_params["path"])
        target = (active.web_dist / "assets" / relative).resolve()
        root = active.web_dist.resolve()
        if root not in target.parents or not target.is_file():
            return JSONResponse({"error": "not_found"}, status_code=404)
        return FileResponse(target)

    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/capabilities", capabilities),
            Route("/api/contracts", contracts),
            Route("/api/sessions", sessions),
            Route("/api/sessions/{session:str}/snapshot", live_snapshot),
            Route(
                "/api/sessions/{session:str}/control",
                live_control,
                methods=["POST"],
            ),
            Route(
                "/api/sessions/{session:str}/{endpoint:str}",
                gateway_events,
            ),
            Route("/api/runs", runs),
            Route("/api/recorded-sessions", recorded_session_catalog),
            Route(
                "/api/recorded-sessions/{run_id:str}",
                recorded_session,
            ),
            Route("/api/runs/{run_id:str}/investigation", investigation),
            Route("/api/runs/{run_id:str}/knowledge", knowledge),
            Route("/api/diagnostic-history", history),
            Route("/api/incidents/export", export_incident, methods=["POST"]),
            Route("/api/comparisons", comparisons),
            Route("/api/world/atlas", world_atlas),
            Route(
                "/api/comparisons/{comparison_id:str}",
                comparison,
            ),
            Route("/api/ask", ask, methods=["POST"]),
            Route("/assets/{path:path}", asset),
            Route("/", index),
            Route("/{path:path}", index),
        ]
    )


def _upstream_error(error: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "error": "gateway_unavailable",
            "detail": str(error),
        },
        status_code=503,
    )


def _runtime_error(error: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "error": "runtime_unavailable",
            "detail": str(error),
        },
        status_code=503,
    )


def _runtime_events(
    request: Request,
    runtime: RuntimeSource,
    session_id: str,
    endpoint: str,
) -> StreamingResponse:
    after_value = request.query_params.get("after")
    header_value = request.headers.get("last-event-id")
    cursor = int(after_value or header_value or "0")
    limit_value = request.query_params.get("limit")
    limit = int(limit_value) if limit_value else None
    tail = request.query_params.get("tail", "1") != "0"

    async def body():
        nonlocal cursor
        delivered = 0
        while True:
            try:
                events = runtime.events(
                    session_id,
                    after=cursor,
                    limit=(
                        None
                        if limit is None
                        else max(0, limit - delivered)
                    ),
                )
            except RuntimeSourceError:
                return
            for event in events:
                cursor = event.seq
                delivered += 1
                yield serialize_event(event)
                if limit is not None and delivered >= limit:
                    return
            if endpoint == "replay" or not tail:
                return
            try:
                selected = runtime.session(session_id)
            except RuntimeSourceError:
                return
            if selected is None or (
                not selected.live and cursor >= selected.latest_seq
            ):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    arguments = parser.parse_args()
    uvicorn.run(
        create_app(),
        host=arguments.host,
        port=arguments.port,
    )


if __name__ == "__main__":
    main()
