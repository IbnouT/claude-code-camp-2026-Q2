"""Discover configured data sources and product capabilities."""

from __future__ import annotations

from pathlib import Path

import httpx
from mud_gateway.contracts import contract_digest

from .contracts import (
    LiveVoiceCapability,
    ObservatoryCapabilities,
    SourceStatus,
)
from .settings import Settings
from .sources.gateway import gateway_status
from .sources.runtime import RuntimeSource

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
    "knowledge-overview",
    "incident-capsules",
    "offline-reopen",
    "annotations",
    "diagnostic-history",
)


async def discover(
    settings: Settings,
    *,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> ObservatoryCapabilities:
    runtime = (
        None
        if settings.runtime_root is None
        else RuntimeSource(settings.runtime_root)
    )
    gateway = (
        SourceStatus(
            id="gateway",
            label="Gateway journals",
            state="ready",
            detail="Registered player sessions are discoverable",
            contract_digest=contract_digest(),
        )
        if runtime is not None and runtime.available
        else await gateway_status(
            settings.gateway_url,
            transport=gateway_transport,
        )
    )
    sources = [
        gateway,
        (
            SourceStatus(
                id="agent",
                label="Agent events",
                state="ready",
                detail="Registered session agent logs are discoverable",
            )
            if runtime is not None and runtime.available
            else _path_source(
                "agent",
                "Agent events",
                settings.agent_events,
            )
        ),
        _path_source(
            "benchmark",
            "Benchmark evidence",
            settings.benchmark_root,
        ),
        _knowledge_source(settings.runtime_root),
        _path_source(
            "world",
            "Observer world atlas",
            settings.world_root,
        ),
    ]
    voice = _voice_capability(settings, runtime)
    return ObservatoryCapabilities(
        sources=tuple(sources),
        features=tuple(
            feature
            for feature in (
                FEATURES
                + (
                    ("benchmark-execution",)
                    if settings.experiment_execution_enabled
                    else ()
                )
                + (
                    ("copilot-model",)
                    if (
                settings.copilot_model
                and settings.copilot_api_key
                and settings.copilot_spend_cap > 0
                and settings.copilot_input_rate > 0
                and settings.copilot_output_rate > 0
                    )
                    else ()
                )
                + (("live-voice",) if voice.enabled else ())
            )
            if feature not in settings.disabled_features
        ),
        voice=voice,
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
            detail="Configured source is unavailable",
        )
    return SourceStatus(
        id=source_id,
        label=label,
        state="ready",
        detail="Configured source is readable",
    )


def _knowledge_source(runtime_root: Path | None) -> SourceStatus:
    if runtime_root is None:
        return SourceStatus(
            id="knowledge",
            label="Knowledge store",
            state="disabled",
            detail="BOUKENSHA_DIR is not configured",
        )
    profiles = runtime_root / "profiles"
    if not profiles.is_dir():
        return SourceStatus(
            id="knowledge",
            label="Knowledge store",
            state="unavailable",
            detail="No player profiles are retained",
        )
    stores = tuple(profiles.glob("*/knowledge.db"))
    if not stores:
        return SourceStatus(
            id="knowledge",
            label="Knowledge store",
            state="unavailable",
            detail="No player knowledge store is retained yet",
        )
    return SourceStatus(
        id="knowledge",
        label="Knowledge store",
        state="ready",
        detail=f"{len(stores)} per-player knowledge stores are readable",
    )


def _voice_capability(
    settings: Settings,
    runtime: RuntimeSource | None,
) -> LiveVoiceCapability:
    if "live-voice" in settings.disabled_features:
        return LiveVoiceCapability(
            enabled=False,
            detail="Voice is disabled by local policy",
        )
    if runtime is None or not runtime.available:
        return LiveVoiceCapability(
            enabled=False,
            detail="Voice requires a registered Live session",
        )
    if not settings.voice_api_key:
        return LiveVoiceCapability(
            enabled=False,
            detail="OPENAI_API_KEY is not configured",
        )
    if settings.voice_cache_root is None:
        return LiveVoiceCapability(
            enabled=False,
            detail="Voice cache is not configured",
        )
    return LiveVoiceCapability(
        enabled=True,
        detail="Voice is available for the selected Agent thinking excerpt",
        endpoint_template="/api/sessions/{session}/voice",
    )
