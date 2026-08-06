"""Model-asserted state facts.

The agent's required per-response fields land here as belief-layer facts
with explicit model provenance: low confidence, a method naming the
contract, and the current place as subject. A wrong assessment is a visible,
inspectable fact, never a silent miss.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .knowledge_models import EvidenceRef

METHOD = "model_state_fields"
PARSER_VERSION = "state-fields-1"


def record_state_fields(
    store: Any,
    projector: Any,
    session_id: str,
    source_seq: int,
    *,
    perceive: str | None = None,
    threat: str | None = None,
    learned: str | None = None,
) -> dict[str, Any]:
    """Write the asserted fields as facts. Returns what was recorded."""
    place = getattr(projector, "current_place_id", None)
    recorded: dict[str, Any] = {"place": place}
    evidence = EvidenceRef(
        session_id=session_id,
        source_seq=source_seq,
        wire_digest="model",
        parser_version=PARSER_VERSION,
        method=METHOD,
        observed_at=time.time(),
    )
    transaction = f"state-fields-{uuid.uuid4().hex[:12]}"

    def note(subject: str, predicate: str, value: Any) -> None:
        store.assert_fact(
            subject,
            predicate,
            value,
            layer="belief",
            confidence="low",
            evidence=evidence,
            transaction_id=transaction,
        )
        recorded[predicate] = value

    if place is not None and perceive in ("dark", "clear"):
        note(place, "model.perceive", perceive)
    if place is not None and threat:
        note(place, "model.threat", threat)
    if learned:
        subject = place if place is not None else f"session:{session_id}"
        note(subject, "model.note", learned)
    return recorded


SERVICE_KINDS = (
    "bank", "shop", "guild", "fountain", "food", "grinding", "healer",
)


def record_service(
    store: Any,
    projector: Any,
    session_id: str,
    source_seq: int,
    *,
    kind: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Record the current place as offering one recognized service."""
    place = getattr(projector, "current_place_id", None)
    recorded: dict[str, Any] = {"place": place, "kind": kind}
    if kind not in SERVICE_KINDS or place is None:
        recorded["stored"] = False
        return recorded
    evidence = EvidenceRef(
        session_id=session_id,
        source_seq=source_seq,
        wire_digest="model",
        parser_version=PARSER_VERSION,
        method=METHOD,
        observed_at=time.time(),
    )
    store.assert_fact(
        place,
        f"service.{kind}",
        detail or True,
        layer="belief",
        confidence="low",
        evidence=evidence,
        transaction_id=f"service-{uuid.uuid4().hex[:12]}",
    )
    recorded["stored"] = True
    return recorded
