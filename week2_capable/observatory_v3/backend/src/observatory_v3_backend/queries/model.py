"""Optional direct-REST translation into the typed observatory query language."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ..contracts import QueryOperation
from ..redaction import sanitize_evidence


class Translation(BaseModel):
    """The only output accepted from the optional model translator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: QueryOperation | Literal["unsupported"]


class GroundedSummary(BaseModel):
    """The only accepted shape for an optional evidence summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class TranslationResult:
    operation: QueryOperation | Literal["unsupported"]
    cost_usd: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    citations: tuple[str, ...]
    cost_usd: float
    input_tokens: int
    output_tokens: int


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
                "summarize_live, list_position_candidates, compare_rendering, "
                "list_experiment_samples, search_evidence, search_knowledge, "
                "or unsupported. "
                "diagnose_stop covers why an agent stopped, completion beliefs, "
                "and final-decision autopsies. list_position_candidates covers "
                "ambiguous or low-confidence location. compare_rendering covers "
                "raw, minimal, or full policy comparison. summarize_live covers "
                "current activity. list_experiment_samples covers jobs, cohorts, "
                "and samples. search_evidence covers exact retained records. "
                "search_knowledge covers learned state. Return no other key. "
                "You have no access to evidence and must not answer the question."
            ),
            "messages": [{"role": "user", "content": _safe_text(question)}],
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
        translation = Translation.model_validate({"operation": match.group(1)})
        if translation.operation not in {
            "diagnose_stop",
            "summarize_live",
            "list_position_candidates",
            "compare_rendering",
            "list_experiment_samples",
            "search_evidence",
            "search_knowledge",
            "unsupported",
        }:
            raise ValueError("model selected an operation outside the allowlist")
        usage = dict(payload.get("usage") or {})
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cost = (
            input_tokens * self.input_rate + output_tokens * self.output_rate
        ) / 1_000_000
        return TranslationResult(
            translation.operation,
            cost,
            input_tokens,
            output_tokens,
        )

    async def summarize(
        self,
        *,
        question: str,
        answer: str,
        claims: tuple[tuple[str, tuple[str, ...]], ...],
        citations: tuple[tuple[str, str], ...],
        missing: tuple[str, ...],
    ) -> SummaryResult:
        """Summarize only the supplied sanitized evidence identifiers."""

        allowed = {citation_id for citation_id, _excerpt in citations}
        evidence = {
            "question": _safe_text(question),
            "deterministic_answer": _safe_text(answer),
            "claims": [
                {
                    "text": _safe_text(text),
                    "citations": list(claim_citations),
                }
                for text, claim_citations in claims
            ],
            "evidence": [
                {
                    "id": citation_id,
                    "excerpt": _safe_text(excerpt),
                }
                for citation_id, excerpt in citations
            ],
            "missing": [_safe_text(item) for item in missing],
        }
        body = {
            "model": self.model,
            "max_tokens": 160,
            "temperature": 0,
            "system": (
                "Summarize only the supplied deterministic answer and "
                "evidence. Do not add facts. Return JSON only with summary "
                "and citations. Every citation must be an exact supplied ID. "
                "Call missing evidence a gap, never a fact."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        evidence,
                        separators=(",", ":"),
                    ),
                }
            ],
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
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            raise ValueError("model summary did not contain a JSON object")
        summary = GroundedSummary.model_validate_json(match.group(0))
        if not summary.summary.strip():
            raise ValueError("model summary was empty")
        if any(citation not in allowed for citation in summary.citations):
            raise ValueError("model summary cited evidence outside the result")
        if allowed and not summary.citations:
            raise ValueError("model summary omitted evidence citations")
        usage = dict(payload.get("usage") or {})
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cost = (
            input_tokens * self.input_rate + output_tokens * self.output_rate
        ) / 1_000_000
        return SummaryResult(
            summary=summary.summary.strip(),
            citations=summary.citations,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _safe_text(value: str) -> str:
    return str(sanitize_evidence(value))
