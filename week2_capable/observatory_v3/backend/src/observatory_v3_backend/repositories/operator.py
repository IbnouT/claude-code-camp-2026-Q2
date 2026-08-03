"""Durable Goal revision and Nudge evidence reads."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from ..errors import MalformedSourceError
from ..models import OperatorSnapshot, SessionRecord

MAX_OPERATOR_BYTES = 4 * 1024 * 1024
MAX_OPERATOR_MESSAGES = 1_000


def operator_history_digest(
    messages: tuple[dict[str, Any], ...],
) -> str:
    """Digest immutable operator request history in retained file order."""
    history = tuple(
        {
            "request_id": message["request_id"],
            "action": message["action"],
            "instruction": message["instruction"],
            "sent_at": message["sent_at"],
        }
        for message in messages
    )
    canonical = json.dumps(
        history,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(canonical).hexdigest()


def operator_application_state(
    messages: tuple[dict[str, Any], ...],
) -> str:
    """Serialize bounded request application state for monotonic validation."""
    state = tuple(
        {
            "request_id": message["request_id"],
            "applied_iteration": message["applied_iteration"],
            "applied_at": message["applied_at"],
        }
        for message in messages
    )
    return json.dumps(
        state,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def operator_transition_fault(
    previous_state: str,
    messages: tuple[dict[str, Any], ...],
) -> str | None:
    """Reject loss or mutation of an already committed application boundary."""
    previous = json.loads(previous_state)
    if not isinstance(previous, list):
        raise ValueError("committed operator state is not a list")
    if len(messages) < len(previous):
        return "operator_snapshot_truncated"
    for index, retained in enumerate(previous):
        if not isinstance(retained, dict):
            raise ValueError("committed operator entry is not an object")
        current = messages[index]
        if retained.get("request_id") != current["request_id"]:
            return "operator_snapshot_history_changed"
        retained_iteration = retained.get("applied_iteration")
        retained_at = retained.get("applied_at")
        if retained_iteration is None and retained_at is None:
            continue
        if (
            retained_iteration != current["applied_iteration"]
            or retained_at != current["applied_at"]
        ):
            return "operator_application_boundary_changed"
    return None


class OperatorRepository:
    """Read bounded operator messages without accepting malformed evidence."""

    def __init__(self, session: SessionRecord) -> None:
        self.source = session.session_dir / "operator-messages.json"

    def messages(self, *, limit: int = 250) -> tuple[dict[str, Any], ...]:
        """Return retained messages in file order."""
        if not 1 <= limit <= 1_000:
            raise ValueError("operator limit must be between 1 and 1,000")
        return self.snapshot().messages[:limit]

    def snapshot(self) -> OperatorSnapshot:
        """Read and validate the complete retained file once."""
        if not self.source.is_file():
            return OperatorSnapshot(messages=(), revision=sha256(b"").hexdigest())
        try:
            with self.source.open("rb") as handle:
                encoded = handle.read(MAX_OPERATOR_BYTES + 1)
            if len(encoded) > MAX_OPERATOR_BYTES:
                raise MalformedSourceError(
                    self.source,
                    "operator message file exceeds 4 MiB",
                )
            value = json.loads(encoded)
        except MalformedSourceError:
            raise
        except (OSError, json.JSONDecodeError) as error:
            raise MalformedSourceError(
                self.source,
                "operator message file is invalid JSON",
            ) from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise MalformedSourceError(
                self.source,
                "operator message version is unsupported",
            )
        raw_messages = value.get("messages")
        if not isinstance(raw_messages, list):
            raise MalformedSourceError(
                self.source,
                "operator messages must be a list",
            )
        if len(raw_messages) > MAX_OPERATOR_MESSAGES:
            raise MalformedSourceError(
                self.source,
                "operator messages exceed 1,000 records",
            )
        messages: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for index, message in enumerate(raw_messages):
            if not isinstance(message, dict):
                raise MalformedSourceError(
                    self.source,
                    f"operator message {index} is not an object",
                )
            request_id = message.get("request_id")
            action = message.get("action")
            instruction = message.get("instruction")
            sent_at = message.get("sent_at")
            applied_iteration = message.get("applied_iteration")
            applied_at = message.get("applied_at")
            if (
                not isinstance(request_id, str)
                or action not in {"guide", "revise"}
                or not isinstance(instruction, str)
                or not isinstance(sent_at, str)
                or (
                    applied_iteration is not None
                    and not isinstance(applied_iteration, int)
                )
                or (applied_at is not None and not isinstance(applied_at, str))
            ):
                raise MalformedSourceError(
                    self.source,
                    f"operator message {index} has invalid fields",
                )
            normalized = {
                "request_id": request_id,
                "action": action,
                "instruction": instruction,
                "sent_at": sent_at,
                "applied_iteration": applied_iteration,
                "applied_at": applied_at,
            }
            previous = seen.get(request_id)
            if previous is not None:
                if previous != normalized:
                    raise MalformedSourceError(
                        self.source,
                        f"operator request {request_id!r} is contradictory",
                    )
                continue
            seen[request_id] = normalized
            messages.append(normalized)
        return OperatorSnapshot(
            messages=tuple(messages),
            revision=sha256(encoded).hexdigest(),
        )
