"""Canonical contracts shared by the gateway and its read-only consumers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 1


class EventEnvelope(BaseModel):
    """One committed event as exposed through live and replay transports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(gt=0)
    session: str = Field(min_length=1)
    at: float
    kind: str = Field(min_length=1)
    trace_id: str | None = None
    data: dict[str, Any]


class GatewayCapabilities(BaseModel):
    """Runtime promises a consumer can rely on for one gateway instance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: int = CONTRACT_VERSION
    contract_digest: str
    delivery: Literal["at-least-once"] = "at-least-once"
    cursor: Literal["session-sequence"] = "session-sequence"
    live_cross_process: bool = True
    unknown_events_preserved: bool = True
    endpoints: tuple[str, ...] = (
        "/sessions",
        "/sessions/{session}/events",
        "/sessions/{session}/replay",
        "/sessions/{session}/wire",
        "/capabilities",
        "/contracts",
    )


class EvidenceQuery(BaseModel):
    """A safe, serializable evidence selection for projections and search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session: str = Field(min_length=1)
    after: int = Field(default=0, ge=0)
    through: int | None = Field(default=None, gt=0)
    kinds: tuple[str, ...] = ()
    trace_id: str | None = None


class Gap(BaseModel):
    """An inclusive missing range in an otherwise ordered projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    first: int = Field(gt=0)
    last: int = Field(gt=0)


class ProjectionCursor(BaseModel):
    """The reproducible boundary and completeness of a derived projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session: str = Field(min_length=1)
    through_seq: int = Field(ge=0)
    event_count: int = Field(ge=0)
    completeness: Literal["complete", "partial", "gap"]
    gaps: tuple[Gap, ...] = ()
    unknown_kinds: tuple[str, ...] = ()
    contract_digest: str


def contract_schemas() -> dict[str, Any]:
    """Return the canonical JSON Schemas consumed by generated clients."""

    return {
        "event": EventEnvelope.model_json_schema(),
        "capabilities": GatewayCapabilities.model_json_schema(),
        "query": EvidenceQuery.model_json_schema(),
        "projection": ProjectionCursor.model_json_schema(),
    }


def contract_digest() -> str:
    """Identify one exact canonical contract bundle."""

    canonical = json.dumps(
        contract_schemas(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()[:16]


def capabilities() -> GatewayCapabilities:
    """Build the gateway capability manifest."""

    return GatewayCapabilities(contract_digest=contract_digest())
