"""Read-only gateway access without duplicating gateway truth."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

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


class GatewaySource:
    """Proxy durable gateway evidence while preserving its wire contract."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self.transport = transport

    async def sessions(self) -> dict[str, Any]:
        payload = await self.json("/sessions")
        if not isinstance(payload.get("sessions"), list):
            raise ValueError("gateway returned an invalid sessions payload")
        return payload

    async def json(self, path: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(path)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"gateway returned an invalid payload for {path}")
        return payload

    @asynccontextmanager
    async def stream(
        self,
        path: str,
        *,
        query: list[tuple[str, str]],
    ) -> AsyncIterator[httpx.Response]:
        client = self._client()
        await client.__aenter__()
        try:
            request = client.build_request("GET", path, params=query)
            response = await client.send(request, stream=True)
            response.raise_for_status()
            try:
                yield response
            finally:
                await response.aclose()
        finally:
            await client.__aexit__(None, None, None)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            transport=self.transport,
            timeout=httpx.Timeout(10.0, read=None),
        )
