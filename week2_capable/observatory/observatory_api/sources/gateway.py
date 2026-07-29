"""Gateway capability discovery without duplicating gateway truth."""

from __future__ import annotations

import httpx

from ..contracts import SourceStatus


async def gateway_status(
    base_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SourceStatus:
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=1.5,
        ) as client:
            response = await client.get("/capabilities")
            response.raise_for_status()
            payload = response.json()
        return SourceStatus(
            id="gateway",
            label="Gateway journal",
            state="ready",
            detail="Live sequence and replay are available",
            contract_digest=str(payload["contract_digest"]),
        )
    except (httpx.HTTPError, KeyError, ValueError):
        return SourceStatus(
            id="gateway",
            label="Gateway journal",
            state="unavailable",
            detail=f"No gateway responded at {base_url}",
        )
