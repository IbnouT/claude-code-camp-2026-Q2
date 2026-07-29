"""Local read API and static host for the Boukensha observatory."""

from __future__ import annotations

import argparse
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from .capabilities import discover
from .settings import Settings


def create_app(settings: Settings | None = None) -> Starlette:
    active = settings or Settings.from_environment()

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "read_only": True})

    async def capabilities(_request: Request) -> JSONResponse:
        result = await discover(active)
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
            Route("/assets/{path:path}", asset),
            Route("/", index),
            Route("/{path:path}", index),
        ]
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
