"""Sanitized, portable observatory incident capsules."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from .contracts import (
    DiagnosticHistory,
    IncidentCapsule,
    IncidentExportRequest,
    IncidentPayload,
    IncidentSelection,
    Investigation,
    KnowledgeOverview,
    RedactionReport,
)
from .redaction import redact_question

LOCAL_PATH = re.compile(
    r"(?:(?:/Users|/home|/private|/var/folders|/tmp)/[^\s\"']+|"
    r"[A-Za-z]:\\\\Users\\\\[^\s\"']+)"
)
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}


def build_capsule(
    request: IncidentExportRequest,
    investigation: Investigation,
    knowledge: KnowledgeOverview,
    history: DiagnosticHistory,
    revision: str,
) -> IncidentCapsule:
    """Build one integrity-sealed export from already sanitized evidence."""

    replacements = 0

    def sanitize(value: Any, key: str = "") -> Any:
        nonlocal replacements
        if key.casefold() in SENSITIVE_KEYS:
            replacements += 1
            return "[REDACTED]"
        if isinstance(value, str):
            redacted = redact_question(value)
            redacted = LOCAL_PATH.sub("[LOCAL_PATH]", redacted)
            if redacted != value:
                replacements += 1
            return redacted
        if isinstance(value, dict):
            return {
                str(item_key): sanitize(item_value, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    safe_investigation = Investigation.model_validate(
        sanitize(investigation.model_dump(mode="json"))
    )
    safe_annotations = tuple(
        annotation.model_copy(update={"text": sanitize(annotation.text)})
        for annotation in request.annotations
    )
    payload = IncidentPayload(
        generated_at=datetime.now(UTC).isoformat(),
        title=f"{investigation.run.journey} · {investigation.run.label}",
        source_versions={
            "capsule": "1",
            "investigation": "1",
            "world_projection": "1",
            "diagnostics": "1",
            "repository": revision,
        },
        investigation=safe_investigation,
        knowledge=knowledge,
        history=history,
        selection=IncidentSelection(
            selected_sequence=request.selected_sequence,
            diagnostic_id=request.diagnostic_id,
        ),
        annotations=safe_annotations,
        redaction=RedactionReport(
            policy="credentials and local paths removed at export",
            replacements=replacements,
        ),
    )
    canonical = canonical_payload(payload)
    return IncidentCapsule(
        digest=hashlib.sha256(canonical).hexdigest(),
        payload=payload,
    )


def canonical_payload(payload: IncidentPayload) -> bytes:
    """Serialize the payload exactly as browser integrity checks expect."""

    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
