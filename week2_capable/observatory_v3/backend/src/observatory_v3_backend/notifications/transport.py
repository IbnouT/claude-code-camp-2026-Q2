"""Typed SSE framing for bounded resource notifications."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from starlette.requests import Request
from starlette.responses import StreamingResponse

from ..api_v1.contracts import ResourceChangeTarget
from .hub import ResourceNotificationHub, ResourceNotificationSubscription
from .service import SessionNotificationLease, SessionNotificationService

SSE_RETRY_MS = 1_000


async def session_notification_response(
    request: Request,
    *,
    hub: ResourceNotificationHub,
    service: SessionNotificationService,
) -> StreamingResponse:
    """Open one selected-session notification stream."""
    session_id = request.query_params.get("session_id", "")
    lease = await service.acquire(session_id)
    try:
        last_event_id = request.headers.get("last-event-id")
        if last_event_id is not None:
            await lease.wait_ready()
        subscription = await hub.subscribe(
            last_event_id,
            target_filter=_session_filter(session_id),
        )
    except BaseException:
        await lease.close()
        raise
    return StreamingResponse(
        _event_body(request, subscription, lease),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_body(
    request: Request,
    subscription: ResourceNotificationSubscription,
    lease: SessionNotificationLease,
) -> AsyncIterator[bytes]:
    try:
        async for envelope in subscription:
            if await request.is_disconnected():
                return
            payload = envelope.payload
            yield (
                f"id: {envelope.event_id}\n"
                f"event: {payload.event}\n"
                f"retry: {SSE_RETRY_MS}\n"
                f"data: {payload.model_dump_json()}\n\n"
            ).encode()
    finally:
        await subscription.close()
        await lease.close()


def _session_filter(
    session_id: str,
) -> Callable[[ResourceChangeTarget], bool]:
    prefix = f"session:{session_id}:"

    def matches(target: ResourceChangeTarget) -> bool:
        return (
            target.resource_id.startswith(prefix)
            or target.resource_kind == "session_catalog"
        )

    return matches
