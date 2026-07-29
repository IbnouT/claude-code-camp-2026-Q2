"""Optional direct-REST translation into the typed observatory query language."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict

from ..redaction import redact_question


class Translation(BaseModel):
    """The only output accepted from the optional model translator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str


@dataclass(frozen=True)
class TranslationResult:
    operation: str
    cost_usd: float


class ModelTranslator:
    """Translate a question without giving the model evidence or data access."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        input_rate: float,
        output_rate: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.transport = transport

    async def translate(self, question: str) -> TranslationResult:
        body = {
            "model": self.model,
            "max_tokens": 80,
            "temperature": 0,
            "system": (
                "Translate the question into one permitted read-only operation. "
                "Return JSON only with operation equal to diagnose_stop, "
                "list_position_candidates, compare_rendering, or unsupported. "
                "diagnose_stop covers why an agent stopped, completion beliefs, "
                "and final-decision autopsies. list_position_candidates covers "
                "ambiguous or low-confidence location. compare_rendering covers "
                "raw, minimal, or full policy comparison. Return no other key. "
                "You have no access to evidence and must not answer the question."
            ),
            "messages": [{"role": "user", "content": redact_question(question)}],
        }
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=20,
        ) as client:
            response = await client.post(
                self.endpoint,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        payload = response.json()
        content = payload.get("content") or []
        text = "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
        match = re.search(r'"operation"\s*:\s*"([^"]+)"', text)
        if match is None:
            raise ValueError("model translation did not contain an operation")
        translation = Translation(operation=match.group(1))
        if translation.operation not in {
            "diagnose_stop",
            "list_position_candidates",
            "compare_rendering",
            "unsupported",
        }:
            raise ValueError("model selected an operation outside the allowlist")
        usage = dict(payload.get("usage") or {})
        cost = (
            float(usage.get("input_tokens") or 0) * self.input_rate
            + float(usage.get("output_tokens") or 0) * self.output_rate
        ) / 1_000_000
        return TranslationResult(translation.operation, cost)
