"""Discover configured data sources and product capabilities."""

from __future__ import annotations

from pathlib import Path

import httpx

from .contracts import ObservatoryCapabilities, SourceStatus
from .settings import Settings
from .sources.gateway import gateway_status

FEATURES = (
    "live",
    "replay",
    "time-travel",
    "provenance",
    "diagnostics",
    "world",
    "compare",
    "counterfactual",
    "query",
    "copilot-local",
)


async def discover(
    settings: Settings,
    *,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> ObservatoryCapabilities:
    sources = [
        await gateway_status(
            settings.gateway_url,
            transport=gateway_transport,
        ),
        _path_source(
            "agent",
            "Agent events",
            settings.agent_events,
        ),
        _path_source(
            "benchmark",
            "Benchmark evidence",
            settings.benchmark_root,
        ),
        _path_source(
            "knowledge",
            "Knowledge store",
            settings.knowledge_db,
        ),
    ]
    return ObservatoryCapabilities(
        sources=tuple(sources),
        features=(
            FEATURES + ("copilot-model",)
            if (
                settings.copilot_model
                and settings.copilot_api_key
                and settings.copilot_spend_cap > 0
                and settings.copilot_input_rate > 0
                and settings.copilot_output_rate > 0
            )
            else FEATURES
        ),
    )


def _path_source(
    source_id: str,
    label: str,
    path: Path | None,
) -> SourceStatus:
    if path is None:
        return SourceStatus(
            id=source_id,
            label=label,
            state="disabled",
            detail="Not configured",
        )
    if not path.exists():
        return SourceStatus(
            id=source_id,
            label=label,
            state="unavailable",
            detail=f"Configured path does not exist: {path}",
        )
    return SourceStatus(
        id=source_id,
        label=label,
        state="ready",
        detail=str(path),
    )
