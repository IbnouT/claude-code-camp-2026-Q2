"""Canonical internal source cursor and opaque client token."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from ..index.models import SourceWatermark

CURSOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class CompositeSourceCursor:
    """All retained coordinates required for one coherent session prefix."""

    registry_updated_at: str
    lifecycle_sequence: int
    gateway_session_id: str
    gateway_source_id: str
    gateway_sequence: int
    agent_source_id: str
    agent_offset: int
    agent_next_line: int
    operator_source_id: str
    operator_revision: str
    operator_message_count: int
    operator_history_digest: str
    operator_state_digest: str
    experiment_revision: str | None
    knowledge_revision: str | None

    @classmethod
    def from_watermark(
        cls,
        watermark: SourceWatermark,
    ) -> CompositeSourceCursor:
        """Build the cursor from one atomically committed index watermark."""
        return cls(
            registry_updated_at=watermark.registry_updated_at,
            lifecycle_sequence=watermark.lifecycle_sequence,
            gateway_session_id=watermark.gateway_session_id,
            gateway_source_id=watermark.gateway_source_id,
            gateway_sequence=watermark.gateway_sequence,
            agent_source_id=watermark.agent_source_id,
            agent_offset=watermark.agent_offset,
            agent_next_line=watermark.agent_next_line,
            operator_source_id=watermark.operator_source_id,
            operator_revision=watermark.operator_revision,
            operator_message_count=watermark.operator_message_count,
            operator_history_digest=watermark.operator_history_digest,
            operator_state_digest=sha256(watermark.operator_state.encode()).hexdigest(),
            experiment_revision=watermark.experiment_revision,
            knowledge_revision=watermark.knowledge_revision,
        )

    @property
    def token(self) -> str:
        """Return a non-reversible token without exposing local source identity."""
        canonical = json.dumps(
            {
                "agent_next_line": self.agent_next_line,
                "agent_offset": self.agent_offset,
                "agent_source_id": self.agent_source_id,
                "experiment_revision": self.experiment_revision,
                "gateway_sequence": self.gateway_sequence,
                "gateway_session_id": self.gateway_session_id,
                "gateway_source_id": self.gateway_source_id,
                "knowledge_revision": self.knowledge_revision,
                "lifecycle_sequence": self.lifecycle_sequence,
                "operator_source_id": self.operator_source_id,
                "operator_revision": self.operator_revision,
                "operator_message_count": self.operator_message_count,
                "operator_history_digest": self.operator_history_digest,
                "operator_state_digest": self.operator_state_digest,
                "registry_updated_at": self.registry_updated_at,
                "version": CURSOR_VERSION,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"obc1_{sha256(canonical).hexdigest()}"
