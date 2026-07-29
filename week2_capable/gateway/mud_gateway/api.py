"""ASGI live view and replay surface for gateway journal events."""

from __future__ import annotations

import asyncio
import argparse
import uuid
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .contracts import capabilities as gateway_capabilities
from .contracts import contract_schemas
from .journal import Journal
from .stream import EventHub, canonical_wire


def create_app(journal: Journal) -> Starlette:
    hub = EventHub(journal)

    async def sessions(_request: Request) -> JSONResponse:
        return JSONResponse({"sessions": journal.sessions()})

    async def capabilities(_request: Request) -> JSONResponse:
        return JSONResponse(
            gateway_capabilities().model_dump(mode="json")
        )

    async def contracts(_request: Request) -> JSONResponse:
        return JSONResponse(contract_schemas())

    async def events(request: Request) -> StreamingResponse:
        session = request.path_params["session"]
        after_value = request.query_params.get("after")
        header_value = request.headers.get("last-event-id")
        cursor = int(after_value or header_value) if after_value or header_value else None
        kinds_value = request.query_params.get("kinds")
        kinds = kinds_value.split(",") if kinds_value else None
        tail = request.query_params.get("tail", "1") != "0"
        limit_value = request.query_params.get("limit")
        limit = int(limit_value) if limit_value else None
        subscriber, missed = hub.subscribe(
            uuid.uuid4().hex,
            session,
            kinds=kinds,
            last_event_id=cursor,
        )

        async def body():
            delivered = 0
            try:
                for frame in missed:
                    yield frame
                    delivered += 1
                    if limit is not None and delivered >= limit:
                        return
                if not tail:
                    return
                while True:
                    remaining = (
                        None if limit is None else limit - delivered
                    )
                    frames = subscriber.poll(journal, limit=remaining)
                    if not frames:
                        if await request.is_disconnected():
                            return
                        await asyncio.sleep(0.025)
                        continue
                    for frame in frames:
                        yield frame
                        delivered += 1
                        if limit is not None and delivered >= limit:
                            return
            finally:
                hub.unsubscribe(subscriber)

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def replay(request: Request) -> StreamingResponse:
        session = request.path_params["session"]
        after = int(request.query_params.get("after", "0"))
        kinds_value = request.query_params.get("kinds")
        kinds = kinds_value.split(",") if kinds_value else None

        async def body():
            for frame in hub.replay(session, after=after, kinds=kinds):
                yield frame
                await asyncio.sleep(0)

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    async def wire(request: Request) -> Response:
        session = request.path_params["session"]
        return Response(
            canonical_wire(journal, session),
            media_type="application/octet-stream",
        )

    app = Starlette(
        routes=[
            Route("/sessions", sessions),
            Route("/capabilities", capabilities),
            Route("/contracts", contracts),
            Route("/sessions/{session:str}/events", events),
            Route("/sessions/{session:str}/replay", replay),
            Route("/sessions/{session:str}/wire", wire),
        ]
    )
    app.state.hub = hub
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    journal = Journal(arguments.journal)
    app = create_app(journal)
    try:
        uvicorn.run(app, host=arguments.host, port=arguments.port)
    finally:
        app.state.hub.close()
        journal.close()


if __name__ == "__main__":
    main()
