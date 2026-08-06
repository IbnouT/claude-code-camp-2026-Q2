"""The knowledge capability's required per-response state fields.

The model ends every response with one line in a format this module owns,
so extracting it is protocol decoding of our own contract, never
pattern-matching game prose. A required field with a legal "nothing new"
value cannot be skipped the way an optional tool call can.
"""

from __future__ import annotations

import json
from typing import Any

FIELD_NAMES = ("perceive", "threat", "learned")

CONTRACT = """
## Required state line

End every response with exactly one line of the form:

STATE {"perceive": "clear" | "dark" | "unknown", "threat": null | "<what and how dangerous>", "learned": null | "<one new durable fact>"}

- perceive: whether you can currently make out the room. Use "dark" when
  you cannot see it, "unknown" when unsure.
- threat: null when nothing present threatens you.
- learned: null when this response taught you nothing durable.
The line is required on every response, even when every value is null.
""".strip()


def parse_state_fields(text: str) -> dict[str, Any] | None:
    """The last STATE line's fields, or None when absent or malformed."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("STATE "):
            continue
        try:
            payload = json.loads(stripped[len("STATE "):])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        fields = {name: payload.get(name) for name in FIELD_NAMES}
        perceive = fields["perceive"]
        if perceive not in ("clear", "dark", "unknown"):
            return None
        for name in ("threat", "learned"):
            value = fields[name]
            if value is not None and not isinstance(value, str):
                return None
        return fields
    return None


def strip_state_line(text: str) -> str:
    """The response text without its STATE line, for display surfaces."""
    lines = [
        line for line in text.splitlines()
        if not line.strip().startswith("STATE ")
    ]
    return "\n".join(lines).rstrip()
