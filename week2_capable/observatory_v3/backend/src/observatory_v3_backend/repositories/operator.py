"""Durable Goal revision and Nudge evidence reads."""

from __future__ import annotations

import json
from typing import Any

from ..errors import MalformedSourceError
from ..models import SessionRecord


class OperatorRepository:
    """Read bounded operator messages without accepting malformed evidence."""

    def __init__(self, session: SessionRecord) -> None:
        self.source = session.session_dir / "operator-messages.json"

    def messages(self, *, limit: int = 250) -> tuple[dict[str, Any], ...]:
        """Return retained messages in file order."""
        if not 1 <= limit <= 1_000:
            raise ValueError("operator limit must be between 1 and 1,000")
        if not self.source.is_file():
            return ()
        try:
            value = json.loads(self.source.read_text(encoding="utf-8"))
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
        messages: list[dict[str, Any]] = []
        for index, message in enumerate(raw_messages[:limit]):
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
            messages.append(
                {
                    "request_id": request_id,
                    "action": action,
                    "instruction": instruction,
                    "sent_at": sent_at,
                    "applied_iteration": applied_iteration,
                    "applied_at": applied_at,
                }
            )
        return tuple(messages)
