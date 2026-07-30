"""Sanitized benchmark investigations derived from durable run evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..contracts import (
    DiagnosticRecord,
    EvidenceCitation,
    EvidenceForm,
    EvidenceLens,
    Investigation,
    InvestigationEvent,
    RunSummary,
)
from ..projections.world import project_world


class BenchmarkSource:
    """Read benchmark ledgers and agent traces without exposing local paths."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def runs(self) -> tuple[RunSummary, ...]:
        return tuple(summary for summary, _record, _ledger in self._records())

    def investigation(self, run_id: str) -> Investigation | None:
        for summary, record, ledger in self._records():
            if summary.id == run_id:
                return self._investigate(summary, record, ledger)
        return None

    def _records(self) -> list[tuple[RunSummary, dict[str, Any], Path]]:
        found: list[tuple[RunSummary, dict[str, Any], Path]] = []
        if not self.root.is_dir():
            return found
        for ledger in sorted(self.root.glob("*/attempts.jsonl")):
            if not _inside(ledger, self.root):
                continue
            for line in ledger.read_text(errors="replace").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or "attempt_id" not in record:
                    continue
                summary = _summary(ledger.parent.name, record)
                found.append((summary, record, ledger))
        return sorted(found, key=lambda item: item[0].attempt, reverse=True)

    def _investigate(
        self,
        summary: RunSummary,
        record: dict[str, Any],
        ledger: Path,
    ) -> Investigation:
        agent_path = (
            ledger.parent
            / "attempts"
            / summary.attempt
            / "agent.jsonl"
        )
        rows = _read_agent(agent_path) if _inside(agent_path, self.root) else []
        events, citations = _causal_events(rows)
        diagnostics = _diagnostics(summary, record, rows, citations)
        return Investigation(
            run=summary,
            events=tuple(events),
            diagnostics=tuple(diagnostics),
            citations=tuple(citations.values()),
            lens=_lens(summary, record, rows, citations),
            world=project_world(
                ledger.parent
                / "attempts"
                / summary.attempt
                / "gateway.db"
            ),
        )


def _summary(ledger_name: str, record: dict[str, Any]) -> RunSummary:
    attempt = str(record.get("attempt_id", "unknown"))
    stable = stable_run_id(ledger_name, attempt)
    journey = str(record.get("journey_id", "unknown"))
    mode = str(record.get("result_mode", "unknown"))
    return RunSummary(
        id=stable,
        label=f"{journey} · {mode} · {attempt}",
        journey=journey,
        attempt=attempt,
        success=bool(record.get("success", False)),
        stop_reason=str(record.get("stop_reason", "unknown")),
        iterations=int(record.get("iterations", 0) or 0),
        cost_usd=float(record.get("cost_usd", 0) or 0),
        result_mode=mode,
    )


def stable_run_id(ledger_name: str, attempt: str) -> str:
    """Return the public identifier shared by all recorded-run projections."""

    return hashlib.sha256(
        f"{ledger_name}:{attempt}".encode()
    ).hexdigest()[:16]


def _read_agent(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _causal_events(
    rows: list[dict[str, Any]],
) -> tuple[list[InvestigationEvent], dict[str, EvidenceCitation]]:
    events: list[InvestigationEvent] = []
    citations: dict[str, EvidenceCitation] = {}
    current_iteration: int | None = None
    parent: int | None = None
    for index, row in enumerate(rows, start=1):
        phase = str(row.get("phase", "unknown"))
        if phase == "iteration":
            current_iteration = int(row.get("n", 0))
            parent = None
            continue
        if phase not in {"plan", "response", "tool_call", "tool_result", "turn_end"}:
            continue
        label = _event_label(phase, row)
        citation_id = f"agent:{index}"
        excerpt = _event_excerpt(row)
        if excerpt:
            citations[citation_id] = EvidenceCitation(
                id=citation_id,
                source="agent",
                label=f"Agent log line {index}",
                sequence=index,
                trace_id=_trace_from_result(row),
                excerpt=excerpt[:800],
            )
        event = InvestigationEvent(
            seq=index,
            at=str(row.get("at", "")),
            phase=phase,
            label=label,
            cost_usd=float(row.get("cost_usd", 0) or 0),
            duration_ms=float(row.get("duration_ms", 0) or 0),
            parent=parent,
            citation=citation_id if excerpt else None,
            attributes={
                "iteration": current_iteration,
                "tool": row.get("name"),
                "ok": row.get("ok"),
            },
        )
        events.append(event)
        if phase in {"plan", "response"}:
            parent = index
    return events, citations


def _diagnostics(
    summary: RunSummary,
    record: dict[str, Any],
    rows: list[dict[str, Any]],
    citations: dict[str, EvidenceCitation],
) -> list[DiagnosticRecord]:
    diagnostics: list[DiagnosticRecord] = []
    final_response = _last_row(rows, "response")
    final_seq = rows.index(final_response) + 1 if final_response else len(rows)
    outcome_id = "benchmark:outcome"
    citations[outcome_id] = EvidenceCitation(
        id=outcome_id,
        source="benchmark",
        label="Benchmark outcome",
        excerpt=(
            f"success={summary.success}, stop_reason={summary.stop_reason}, "
            f"iterations={summary.iterations}, cost=${summary.cost_usd:.6f}"
        ),
    )
    if not summary.success and summary.stop_reason == "completed":
        response_id = f"agent:{final_seq}"
        diagnostics.append(
            DiagnosticRecord(
                id="false-completion",
                kind="false_completion",
                severity="critical",
                title="Run ended without satisfying its objective",
                detail=(
                    "The agent ended the turn, but the benchmark's verified "
                    "success predicate remained false."
                ),
                mechanism=(
                    "Triggers when stop_reason is completed while the verified "
                    "journey outcome is unsuccessful."
                ),
                at=final_seq,
                evidence=tuple(
                    item for item in (response_id, outcome_id)
                    if item in citations
                ),
            )
        )

    final_state = record.get("final_state")
    position = final_state.get("position", {}) if isinstance(final_state, dict) else {}
    if isinstance(position, dict) and position.get("confidence") == "ambiguous":
        position_id = "gateway:final-position"
        citations[position_id] = EvidenceCitation(
            id=position_id,
            source="gateway",
            label="Final parsed position",
            trace_id=None,
            excerpt=(
                f"{position.get('title', 'Unknown')}, ambiguous because "
                f"{position.get('method', 'no method was recorded')}"
            ),
        )
        diagnostics.append(
            DiagnosticRecord(
                id="position-ambiguity",
                kind="position_ambiguity",
                severity="warning",
                title="Final position has multiple candidates",
                detail=(
                    "The parser preserved duplicate-room ambiguity instead of "
                    "inventing a unique location."
                ),
                mechanism=(
                    "Triggers when the latest position confidence is ambiguous."
                ),
                at=final_seq,
                evidence=(position_id,),
            )
        )

    room_visits = _room_visits(rows)
    repeated = [(room, count) for room, count in Counter(room_visits).most_common(3) if count >= 5]
    if repeated:
        loop_id = "agent:room-revisits"
        citations[loop_id] = EvidenceCitation(
            id=loop_id,
            source="agent",
            label="Repeated observed rooms",
            excerpt=", ".join(f"{room} ×{count}" for room, count in repeated),
        )
        diagnostics.append(
            DiagnosticRecord(
                id="confusion-loop",
                kind="confusion_loop",
                severity="warning",
                title="Repeated travel stopped adding information",
                detail=", ".join(f"{room} was seen {count} times" for room, count in repeated),
                mechanism=(
                    "Triggers when a room is revisited at least five times in one run."
                ),
                at=final_seq,
                evidence=(loop_id,),
            )
        )

    stall = _longest_stall(room_visits)
    if stall >= 10:
        stall_id = "agent:progress-stall"
        citations[stall_id] = EvidenceCitation(
            id=stall_id,
            source="agent",
            label="Longest no-progress span",
            excerpt=f"{stall} room observations elapsed without discovering a new title.",
        )
        diagnostics.append(
            DiagnosticRecord(
                id="progress-stall",
                kind="stall",
                severity="notice",
                title="Exploration stopped producing new room evidence",
                detail=f"The longest no-new-room span lasted {stall} observations.",
                mechanism=(
                    "Triggers after ten room observations without a new room title."
                ),
                at=final_seq,
                evidence=(stall_id,),
            )
        )

    parse_misses = int(record.get("parse_misses", 0) or 0)
    if parse_misses > 0:
        parse_id = "benchmark:parse-misses"
        citations[parse_id] = EvidenceCitation(
            id=parse_id,
            source="benchmark",
            label="Parser residual",
            excerpt=f"{parse_misses} parser misses were recorded for this attempt.",
        )
        diagnostics.append(
            DiagnosticRecord(
                id="parse-degradation",
                kind="parse_degradation",
                severity="notice",
                title="Parser residual may hide useful evidence",
                detail=f"{parse_misses} source fragments were not classified.",
                mechanism="Triggers when the benchmark records any parser misses.",
                at=final_seq,
                evidence=(parse_id,),
            )
        )
    return diagnostics


def _lens(
    summary: RunSummary,
    record: dict[str, Any],
    rows: list[dict[str, Any]],
    citations: dict[str, EvidenceCitation],
) -> EvidenceLens:
    final_response = _last_row(rows, "response")
    final_result = _last_row(rows, "tool_result")
    final_state = record.get("final_state", {})
    parsed_text = _parsed_summary(final_state)
    believed_text = str(final_response.get("text", ""))[:900] if final_response else ""
    rendered_text = _tool_result_text(final_result)[:900] if final_result else ""
    response_citation = (
        f"agent:{rows.index(final_response) + 1}" if final_response else None
    )
    result_citation = (
        f"agent:{rows.index(final_result) + 1}" if final_result else None
    )
    return EvidenceLens(
        wire=EvidenceForm(
            state="available" if record.get("wire_sequences") else "missing",
            title="Captured MUD frames",
            text=(
                f"{len(record.get('wire_sequences', []))} durable wire references"
                if record.get("wire_sequences")
                else "No wire references were retained."
            ),
            citations=(),
        ),
        parsed=EvidenceForm(
            state="available" if final_state else "missing",
            title="Final parsed state",
            text=parsed_text or "No parsed state was retained.",
            citations=tuple(
                item for item in ("gateway:final-position",)
                if item in citations
            ),
        ),
        rendered=EvidenceForm(
            state="available" if rendered_text else "missing",
            title="Last model-facing observation",
            text=rendered_text or "No rendered observation was retained.",
            citations=(result_citation,) if result_citation in citations else (),
        ),
        believed=EvidenceForm(
            state="available" if believed_text else "missing",
            title="Agent's final account",
            text=believed_text or "No final belief statement was retained.",
            citations=(response_citation,) if response_citation in citations else (),
        ),
        truth=EvidenceForm(
            state="available",
            title="Verified journey outcome",
            text=(
                "Objective satisfied."
                if summary.success
                else "Objective not satisfied by the benchmark predicate."
            ),
            citations=("benchmark:outcome",),
        ),
    )


def _parsed_summary(final_state: Any) -> str:
    if not isinstance(final_state, dict):
        return ""
    room = final_state.get("room")
    position = final_state.get("position")
    vitals = final_state.get("vitals")
    parts: list[str] = []
    if isinstance(room, dict):
        title = room.get("title")
        exits = room.get("exits")
        if title:
            parts.append(f"Room: {title}.")
        if isinstance(exits, list):
            parts.append(f"Exits: {', '.join(str(item) for item in exits) or 'none'}.")
    if isinstance(position, dict):
        parts.append(
            "Position: "
            f"{position.get('confidence', 'unknown')} via "
            f"{position.get('method', 'unknown method')}."
        )
    if isinstance(vitals, dict):
        parts.append(
            "Vitals: "
            f"{vitals.get('hit', '?')} hit, "
            f"{vitals.get('mana', '?')} mana, "
            f"{vitals.get('move', '?')} move."
        )
    return " ".join(parts)


def _room_visits(rows: list[dict[str, Any]]) -> list[str]:
    visits: list[str] = []
    for row in rows:
        if row.get("phase") != "tool_result":
            continue
        text = _tool_result_text(row)
        title = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if title:
            visits.append(title)
    return visits


def _longest_stall(visits: list[str]) -> int:
    seen: set[str] = set()
    current = 0
    longest = 0
    for room in visits:
        key = room.casefold()
        if key not in seen:
            seen.add(key)
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def _last_row(rows: list[dict[str, Any]], phase: str) -> dict[str, Any] | None:
    return next((row for row in reversed(rows) if row.get("phase") == phase), None)


def _event_label(phase: str, row: dict[str, Any]) -> str:
    if phase in {"tool_call", "tool_result"}:
        return str(row.get("name", phase)).removeprefix("tbamud__")
    if phase == "turn_end":
        return "Turn ended"
    if phase == "response":
        return "Model response"
    return "Model plan"


def _event_excerpt(row: dict[str, Any]) -> str:
    if row.get("phase") == "tool_result":
        return _tool_result_text(row)
    if row.get("phase") == "tool_call":
        return json.dumps(row.get("args", {}), separators=(",", ":"), sort_keys=True)
    return str(row.get("text", ""))


def _tool_result_text(row: dict[str, Any] | None) -> str:
    if row is None:
        return ""
    raw = row.get("result")
    if not isinstance(raw, str):
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return str(parsed.get("text", "")) if isinstance(parsed, dict) else raw


def _trace_from_result(row: dict[str, Any]) -> str | None:
    raw = row.get("result")
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    trace = parsed.get("trace_id") if isinstance(parsed, dict) else None
    return str(trace) if trace else None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True
