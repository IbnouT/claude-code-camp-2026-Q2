"""Local read API and static host for the Boukensha observatory."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx
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
from .settings import Settings
from .sources.benchmark import BenchmarkSource
from .sources.comparison import rendering_comparison
from .sources.gateway import GatewaySource


def create_app(
    settings: Settings | None = None,
    *,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    active = settings or Settings.from_environment()
    gateway = GatewaySource(
        active.gateway_url,
        transport=gateway_transport,
    )
    benchmark = (
        BenchmarkSource(active.benchmark_root)
        if active.benchmark_root is not None
        else None
    )

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "read_only": True})

    async def capabilities(_request: Request) -> JSONResponse:
        result = await discover(
            active,
            gateway_transport=gateway_transport,
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def sessions(_request: Request) -> JSONResponse:
        try:
            return JSONResponse(await gateway.sessions())
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

    async def contracts(_request: Request) -> JSONResponse:
        try:
            return JSONResponse(await gateway.json("/contracts"))
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

    async def gateway_events(request: Request) -> Response:
        session = request.path_params["session"]
        endpoint = request.path_params["endpoint"]
        if endpoint not in {"events", "replay"}:
            return JSONResponse({"error": "not_found"}, status_code=404)
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

    async def runs(_request: Request) -> JSONResponse:
        available = () if benchmark is None else benchmark.runs()
        return JSONResponse(
            {"runs": [run.model_dump(mode="json") for run in available]}
        )

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
            Route(
                "/api/sessions/{session:str}/{endpoint:str}",
                gateway_events,
            ),
            Route("/api/runs", runs),
            Route("/api/runs/{run_id:str}/investigation", investigation),
            Route("/api/comparisons", comparisons),
            Route(
                "/api/comparisons/{comparison_id:str}",
                comparison,
            ),
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
