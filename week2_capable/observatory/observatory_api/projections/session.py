"""Build a causal, source-reachable investigation of one recorded session."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from ..contracts import (
    EvidenceForm,
    EvidenceLens,
    RecordedSessionInvestigation,
    RunSummary,
    SessionCostLedger,
    SessionCostPoint,
    SessionDiagnostic,
    SessionEvidenceRecord,
)
from ..sources.recorded_session import (
    GatewayEvidenceRow,
    RecordedSessionBundle,
)
from .world import project_world

RULE_VERSION = "sessions-1"
DIAGNOSTIC_COVERAGE = (
    "false_completion",
    "belief_divergence",
    "position_ambiguity",
    "confusion_loop",
    "progress_stall",
    "parse_degradation",
    "corrective_call_cluster",
    "stale_action",
    "context_churn",
    "instrumentation_gap",
)


def project_recorded_session(
    bundle: RecordedSessionBundle,
) -> RecordedSessionInvestigation:
    """Project retained agent, gateway, and correlated outcome evidence."""

    summary = _summary(bundle)
    objective = _objective(bundle.agent_rows)
    model = _model(bundle.agent_rows)
    agent_records, trace_links = _agent_records(bundle.agent_rows)
    gateway_records, gateway_terminal = _gateway_records(
        bundle.gateway_rows,
        trace_links,
    )
    agent_records = _link_agent_results(
        agent_records,
        trace_links,
        gateway_terminal,
    )
    outcome = _outcome_record(bundle, summary)
    records = tuple((*agent_records, *gateway_records, outcome))
    world = project_world(bundle.gateway_database, objective=objective)
    cost = _cost_ledger(bundle, agent_records)
    capture_gaps = _capture_gaps(bundle, records, cost)
    diagnostics = _diagnostics(
        bundle,
        summary,
        records,
        world.current_confidence,
        world.candidates,
        capture_gaps,
    )
    agent_session = _first_string(bundle.agent_rows, "session_id")
    gateway_session = (
        bundle.gateway_rows[0].session if bundle.gateway_rows else None
    )
    return RecordedSessionInvestigation(
        source_kind="experiment_sample",
        correlation=(
            "This recorded session is linked to its benchmark outcome by the "
            "attempt ledger and attempt directory."
        ),
        run=summary,
        player_id=_player_id(bundle.record.get("profile_id")),
        agent_session_id=agent_session,
        gateway_session_id=gateway_session,
        objective=objective,
        model=model,
        records=records,
        diagnostics=diagnostics,
        diagnostic_coverage=DIAGNOSTIC_COVERAGE,
        lens=_lens(summary, records, world.current_confidence),
        world=world,
        cost=cost,
        capture_gaps=capture_gaps,
    )


def _summary(bundle: RecordedSessionBundle) -> RunSummary:
    record = bundle.record
    journey = str(record.get("journey_id", "unknown"))
    mode = str(record.get("result_mode", "unknown"))
    return RunSummary(
        id=bundle.run_id,
        label=f"{journey} · {mode} · {bundle.attempt_id}",
        journey=journey,
        attempt=bundle.attempt_id,
        success=bool(record.get("success", False)),
        stop_reason=str(record.get("stop_reason", "unknown")),
        iterations=int(record.get("iterations", 0) or 0),
        cost_usd=float(record.get("cost_usd", 0) or 0),
        result_mode=mode,
    )


def _objective(rows: tuple[dict[str, Any], ...]) -> str | None:
    for row in rows:
        if row.get("phase") != "prompt":
            continue
        messages = row.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                ):
                    text = block["text"].strip()
                    if text:
                        return text
    for row in rows:
        task = row.get("task")
        if row.get("phase") in {"config", "session_start"} and isinstance(
            task,
            str,
        ) and task.strip().lower() not in {"player", "agent"}:
            return task
    return None


def _model(rows: tuple[dict[str, Any], ...]) -> str | None:
    for row in rows:
        model = row.get("model")
        if row.get("phase") in {"config", "session_start"} and isinstance(
            model,
            str,
        ):
            return model
    return None


def _agent_records(
    rows: tuple[dict[str, Any], ...],
) -> tuple[list[SessionEvidenceRecord], dict[str, dict[str, str]]]:
    records: list[SessionEvidenceRecord] = []
    iteration: int | None = None
    turn = 0
    iteration_parent: str | None = None
    response_parent: str | None = None
    tool_calls: dict[str, str] = {}
    trace_links: dict[str, dict[str, str]] = {}
    for line, row in enumerate(rows, start=1):
        phase = str(row.get("phase", "unknown"))
        record_id = f"agent:{line}"
        parent = iteration_parent
        if phase == "iteration":
            iteration = _optional_int(row.get("n"))
            iteration_parent = record_id
            response_parent = None
            parent = None
        elif phase == "response":
            turn += 1
            response_parent = record_id
        elif phase == "tool_call":
            parent = response_parent or iteration_parent
            tool_use_id = row.get("id")
            if isinstance(tool_use_id, str):
                tool_calls[tool_use_id] = record_id
        elif phase == "tool_result":
            tool_use_id = row.get("tool_use_id")
            if isinstance(tool_use_id, str):
                parent = tool_calls.get(tool_use_id, parent)
            decoded = _decoded_result(row.get("result"))
            trace_id = decoded.get("trace_id")
            if isinstance(trace_id, str):
                trace_links[trace_id] = {
                    "agent_call": parent or "",
                    "agent_result": record_id,
                }
        form = _agent_form(phase)
        status = _agent_status(row)
        records.append(
            SessionEvidenceRecord(
                id=record_id,
                parent_id=parent,
                source="agent",
                form=form,
                kind=phase,
                label=_agent_label(phase, row),
                sequence=line,
                at=str(row.get("at", "")),
                trace_id=_agent_trace(row),
                iteration=iteration,
                turn=turn or None,
                duration_ms=float(row.get("duration_ms", 0) or 0),
                cost_usd=float(row.get("cost_usd", 0) or 0),
                tokens=_agent_tokens(row),
                status=status,
                preview=_preview(row),
                fields=row,
                source_ref=f"agent log line {line}",
                capture_gaps=(
                    ("No timestamp was retained",)
                    if not row.get("at")
                    else ()
                ),
            )
        )
    return records, trace_links


def _gateway_records(
    rows: tuple[GatewayEvidenceRow, ...],
    trace_links: dict[str, dict[str, str]],
) -> tuple[list[SessionEvidenceRecord], dict[str, str]]:
    records: list[SessionEvidenceRecord] = []
    trace_parent: dict[str, str] = {}
    terminal: dict[str, str] = {}
    for row in rows:
        record_id = f"gateway:{row.sequence}"
        parent: str | None = None
        if row.trace_id:
            if row.kind == "tool_call":
                parent = trace_links.get(row.trace_id, {}).get("agent_call")
            else:
                parent = trace_parent.get(row.trace_id)
            trace_parent[row.trace_id] = record_id
            terminal[row.trace_id] = record_id
        records.append(
            SessionEvidenceRecord(
                id=record_id,
                parent_id=parent or None,
                source="gateway",
                form=_gateway_form(row.kind),
                kind=row.kind,
                label=_gateway_label(row),
                sequence=row.sequence,
                at=datetime.fromtimestamp(row.at, UTC).isoformat(),
                trace_id=row.trace_id,
                room_id=_room_id(row),
                status=_gateway_status(row),
                preview=_preview(row.payload),
                fields=row.payload,
                source_ref=f"gateway event {row.sequence}",
                capture_gaps=(
                    ("No causal trace was retained",)
                    if row.trace_id is None
                    and row.kind not in {
                        "session_open",
                        "session_close",
                        "login",
                        "unsolicited",
                    }
                    else ()
                ),
            )
        )
    return records, terminal


def _link_agent_results(
    records: list[SessionEvidenceRecord],
    trace_links: dict[str, dict[str, str]],
    gateway_terminal: dict[str, str],
) -> list[SessionEvidenceRecord]:
    result_to_trace = {
        links["agent_result"]: trace_id
        for trace_id, links in trace_links.items()
        if links.get("agent_result")
    }
    linked: list[SessionEvidenceRecord] = []
    for record in records:
        trace_id = result_to_trace.get(record.id)
        if trace_id is None:
            linked.append(record)
            continue
        linked.append(
            record.model_copy(
                update={
                    "parent_id": gateway_terminal.get(
                        trace_id,
                        record.parent_id,
                    ),
                    "trace_id": trace_id,
                }
            )
        )
    return linked


def _outcome_record(
    bundle: RecordedSessionBundle,
    summary: RunSummary,
) -> SessionEvidenceRecord:
    status = "complete" if summary.success else "failed"
    return SessionEvidenceRecord(
        id="benchmark:outcome",
        source="benchmark",
        form="truth",
        kind="verified_outcome",
        label=(
            "Verified objective satisfied"
            if summary.success
            else "Verified objective not satisfied"
        ),
        sequence=len(bundle.agent_rows) + len(bundle.gateway_rows) + 1,
        at="",
        status=status,
        preview=(
            f"success={summary.success}, stop_reason={summary.stop_reason}, "
            f"iterations={summary.iterations}, cost=${summary.cost_usd:.6f}"
        ),
        fields={
            "success": summary.success,
            "stop_reason": summary.stop_reason,
            "iterations": summary.iterations,
            "cost_usd": summary.cost_usd,
            "journey_id": summary.journey,
            "attempt_id": summary.attempt,
        },
        source_ref="benchmark attempt outcome",
    )


def _cost_ledger(
    bundle: RecordedSessionBundle,
    agent_records: list[SessionEvidenceRecord],
) -> SessionCostLedger:
    response_rows = [
        (record, row)
        for record, row in zip(agent_records, bundle.agent_rows, strict=True)
        if row.get("phase") == "response"
    ]
    cost_curve = bundle.record.get("cost_curve")
    curve = (
        [float(value) for value in cost_curve]
        if isinstance(cost_curve, list)
        and len(cost_curve) == len(response_rows)
        and all(isinstance(value, (int, float)) for value in cost_curve)
        else None
    )
    points: list[SessionCostPoint] = []
    previous_cumulative = 0.0
    for index, (record, row) in enumerate(response_rows):
        usage = row.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        fresh = _usage_int(row, usage, "input_tokens", "fresh_input_tokens")
        cache_read = _usage_int(
            row,
            usage,
            "cache_read_tokens",
            "cache_read_input_tokens",
        )
        cache_write = _usage_int(
            row,
            usage,
            "cache_write_tokens",
            "cache_creation_input_tokens",
        )
        output = _usage_int(row, usage, "output_tokens")
        raw_cost = record.cost_usd
        if curve is not None:
            cumulative = curve[index]
            attributed_cost = cumulative - previous_cumulative
            previous_cumulative = cumulative
            pricing_source = "attempt_cost_curve"
        else:
            attributed_cost = raw_cost
            pricing_source = "agent_response"
        next_row = (
            response_rows[index + 1][1]
            if index + 1 < len(response_rows)
            else None
        )
        points.append(
            SessionCostPoint(
                record_id=record.id,
                iteration=record.iteration,
                cost_usd=attributed_cost,
                raw_response_cost_usd=raw_cost,
                pricing_source=pricing_source,
                fresh_input_tokens=fresh,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                output_tokens=output,
                context_tokens=fresh + cache_read + cache_write,
                progress=_response_progress(
                    bundle.gateway_rows,
                    row,
                    next_row,
                ),
            )
        )
    total = float(bundle.record.get("cost_usd", 0) or 0)
    response_total = sum(point.cost_usd for point in points)
    raw_response_total = sum(
        point.raw_response_cost_usd for point in points
    )
    delta = total - response_total
    complete = bool(points) and abs(delta) <= 0.000001
    return SessionCostLedger(
        total_usd=total,
        response_total_usd=response_total,
        raw_response_total_usd=raw_response_total,
        reconciliation_delta_usd=delta,
        complete=complete,
        completeness_detail=(
            (
                "Every response is cache-aware repriced from the retained "
                "attempt cost curve and reconciles to the run total."
            )
            if complete
            else (
                "Response costs do not fully reconcile to the retained run "
                f"total. Unattributed delta: ${delta:.6f}."
            )
        ),
        fresh_input_tokens=int(
            bundle.record.get("fresh_input_tokens", 0) or 0
        ),
        cache_read_tokens=int(
            bundle.record.get("cache_read_tokens", 0) or 0
        ),
        cache_write_tokens=int(
            bundle.record.get("cache_write_tokens", 0) or 0
        ),
        output_tokens=int(bundle.record.get("output_tokens", 0) or 0),
        points=tuple(points),
    )


def _response_progress(
    gateway_rows: tuple[GatewayEvidenceRow, ...],
    response: dict[str, Any],
    next_response: dict[str, Any] | None,
) -> str:
    started = _iso_epoch(response.get("at"))
    ended = _iso_epoch(next_response.get("at")) if next_response else None
    if started is None:
        return "Response timestamp is missing, so progress is unattributed"
    window = [
        row
        for row in gateway_rows
        if row.at >= started and (ended is None or row.at < ended)
    ]
    positions = [
        row for row in window
        if row.kind == "position" and isinstance(row.payload.get("title"), str)
    ]
    if positions:
        title = str(positions[-1].payload["title"])
        return f"Reached {title}"
    calls = sum(1 for row in window if row.kind == "tool_call")
    if calls:
        return f"{calls} tool calls, no new position retained"
    return "No gateway progress retained after this response"


def _iso_epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


def _capture_gaps(
    bundle: RecordedSessionBundle,
    records: tuple[SessionEvidenceRecord, ...],
    cost: SessionCostLedger,
) -> tuple[str, ...]:
    gaps: list[str] = []
    if not bundle.agent_rows:
        gaps.append("Agent log is missing")
    if not bundle.gateway_rows:
        gaps.append("Gateway journal is missing")
    if not any(record.form == "wire" for record in records):
        gaps.append("Wire evidence is missing")
    if not any(record.trace_id for record in records if record.source == "agent"):
        gaps.append("Agent-to-gateway trace links are missing")
    if not cost.complete:
        gaps.append(cost.completeness_detail)
    return tuple(gaps)


def _diagnostics(
    bundle: RecordedSessionBundle,
    summary: RunSummary,
    records: tuple[SessionEvidenceRecord, ...],
    position_confidence: str,
    candidates: tuple[str, ...],
    capture_gaps: tuple[str, ...],
) -> tuple[SessionDiagnostic, ...]:
    findings: list[SessionDiagnostic] = []
    final_belief = next(
        (
            record
            for record in reversed(records)
            if record.source == "agent" and record.kind == "response"
        ),
        None,
    )
    outcome = next(record for record in records if record.id == "benchmark:outcome")
    if not summary.success and summary.stop_reason == "completed":
        evidence = tuple(
            record.id for record in (final_belief, outcome) if record is not None
        )
        findings.append(
            _diagnostic(
                kind="false_completion",
                severity="critical",
                title="The run ended before the objective was verified",
                consequence=(
                    "A completed agent turn was treated as a completed journey."
                ),
                threshold="stop reason completed and verified outcome false",
                at_record=final_belief.id if final_belief else outcome.id,
                evidence=evidence,
                alternatives=(
                    "The objective predicate may be incomplete",
                    "The final observation may be missing",
                ),
                affected=("Journey completion", "Agent stop decision"),
            )
        )
        if final_belief is not None:
            findings.append(
                _diagnostic(
                    kind="belief_divergence",
                    severity="critical",
                    title="The final account conflicts with verified outcome",
                    consequence=(
                        "The agent's conclusion cannot be used as objective truth."
                    ),
                    threshold="final belief present and verified outcome false",
                    at_record=final_belief.id,
                    evidence=(final_belief.id, outcome.id),
                    alternatives=(
                        "The final account may describe partial progress",
                    ),
                    affected=("Final answer",),
                )
            )
    if position_confidence == "ambiguous" or candidates:
        position_records = tuple(
            record.id
            for record in records
            if record.source == "gateway" and record.kind == "position"
        )
        if position_records:
            findings.append(
                _diagnostic(
                    kind="position_ambiguity",
                    severity="warning",
                    title="The latest position has multiple candidates",
                    consequence=(
                        "Spatial conclusions cannot assume one unique room."
                    ),
                    threshold="latest position confidence ambiguous",
                    at_record=position_records[-1],
                    evidence=position_records[-3:],
                    alternatives=(
                        "Duplicate titles may represent distinct places",
                        "More exit evidence may resolve the candidate set",
                    ),
                    affected=("Current room", "Journey path"),
                )
            )
    commands = [
        str(record.fields.get("line", "")).casefold()
        for record in records
        if record.source == "gateway" and record.kind == "command"
    ]
    repeated = Counter(commands).most_common(1)
    if repeated and repeated[0][0] and repeated[0][1] >= 5:
        command_records = tuple(
            record.id
            for record in records
            if record.source == "gateway"
            and record.kind == "command"
            and str(record.fields.get("line", "")).casefold() == repeated[0][0]
        )
        findings.append(
            _diagnostic(
                kind="confusion_loop",
                severity="warning",
                title="One command repeated without enough new information",
                consequence="Repeated action consumed turns and model context.",
                threshold="same command recorded at least five times",
                at_record=command_records[-1],
                evidence=command_records[-5:],
                alternatives=(
                    "The repeated command may be required by a long route",
                ),
                affected=("Path efficiency", "Cost per progress"),
            )
        )
    if summary.iterations >= 10 and len({
        record.room_id for record in records if record.room_id
    }) <= max(1, summary.iterations // 10):
        position_records = tuple(
            record.id for record in records if record.kind == "position"
        )
        findings.append(
            _diagnostic(
                kind="progress_stall",
                severity="warning",
                title="Iterations grew without proportional spatial progress",
                consequence="Spend increased while little new world state appeared.",
                threshold="ten or more iterations per distinct observed place",
                at_record=position_records[-1] if position_records else outcome.id,
                evidence=position_records[-5:] or (outcome.id,),
                alternatives=(
                    "The objective may require non-spatial work",
                    "Position capture may be incomplete",
                ),
                affected=("Progress rate", "Cost efficiency"),
            )
        )
    parse_misses = int(bundle.record.get("parse_misses", 0) or 0)
    if parse_misses > 0:
        parse_records = tuple(
            record.id
            for record in records
            if record.kind in {"parse_metric", "unparsed"}
        )
        findings.append(
            _diagnostic(
                kind="parse_degradation",
                severity="notice",
                title="Parser residual may hide useful observations",
                consequence="Derived state may omit evidence present on the wire.",
                threshold="one or more retained parser misses",
                at_record=parse_records[-1] if parse_records else outcome.id,
                evidence=parse_records[-5:] or (outcome.id,),
                alternatives=(
                    "The residual may be decorative output",
                ),
                affected=("Parsed state", "Position confidence"),
            )
        )
    corrections = int(bundle.record.get("corrective_calls", 0) or 0)
    invalid = int(bundle.record.get("invalid_calls", 0) or 0)
    if corrections + invalid >= 3:
        rejected = tuple(
            record.id
            for record in records
            if record.kind in {"tool_rejected", "tool_result"}
            and record.status == "failed"
        )
        findings.append(
            _diagnostic(
                kind="corrective_call_cluster",
                severity="warning",
                title="Tool corrections clustered in this run",
                consequence="Retries consumed turns before useful work resumed.",
                threshold="at least three corrective or invalid calls",
                at_record=rejected[-1] if rejected else outcome.id,
                evidence=rejected[-5:] or (outcome.id,),
                alternatives=(
                    "One external failure may have caused several retries",
                ),
                affected=("Tool reliability", "Cost per progress"),
            )
        )
    occupancy = int(bundle.record.get("occupancy_tokens", 0) or 0)
    fresh = int(bundle.record.get("fresh_input_tokens", 0) or 0)
    if occupancy > 0 and fresh > occupancy * 3 and summary.iterations >= 10:
        response_records = tuple(
            record.id for record in records if record.kind == "response"
        )
        findings.append(
            _diagnostic(
                kind="context_churn",
                severity="notice",
                title="Repeated context dominated fresh input",
                consequence="History was paid for repeatedly across many turns.",
                threshold="fresh input exceeds three times retained occupancy",
                at_record=response_records[-1] if response_records else outcome.id,
                evidence=response_records[-5:] or (outcome.id,),
                alternatives=(
                    "Long context may still contain necessary constraints",
                ),
                affected=("Context efficiency", "Run cost"),
            )
        )
    if capture_gaps:
        gap_records = tuple(
            record.id
            for record in records
            if record.capture_gaps
        )
        findings.append(
            _diagnostic(
                kind="instrumentation_gap",
                severity="notice",
                title="Some conclusions have incomplete instrumentation",
                consequence="Affected values cannot be treated as complete.",
                threshold="one or more required evidence sources or links missing",
                at_record=gap_records[-1] if gap_records else outcome.id,
                evidence=gap_records[-5:] or (outcome.id,),
                alternatives=tuple(capture_gaps[:3]),
                affected=("Evidence completeness",),
            )
        )
    stale = _stale_action(records)
    if stale is not None:
        findings.append(stale)
    return tuple(findings)


def _stale_action(
    records: tuple[SessionEvidenceRecord, ...],
) -> SessionDiagnostic | None:
    last_observation_at: datetime | None = None
    for record in records:
        observed = _parse_time(record.at)
        if observed is None:
            continue
        if record.kind in {"observation", "tool_result"}:
            last_observation_at = observed
        if (
            record.source == "agent"
            and record.kind == "tool_call"
            and last_observation_at is not None
            and (observed - last_observation_at).total_seconds() > 60
        ):
            return _diagnostic(
                kind="stale_action",
                severity="notice",
                title="An action relied on observation older than one minute",
                consequence="The world may have changed before the action ran.",
                threshold="action starts more than 60 seconds after evidence",
                at_record=record.id,
                evidence=(record.id,),
                alternatives=(
                    "The world state may be stable over this interval",
                ),
                affected=("Action freshness",),
            )
    return None


def _diagnostic(
    *,
    kind: str,
    severity: str,
    title: str,
    consequence: str,
    threshold: str,
    at_record: str,
    evidence: tuple[str, ...],
    alternatives: tuple[str, ...],
    affected: tuple[str, ...],
) -> SessionDiagnostic:
    return SessionDiagnostic(
        id=f"{kind}:{at_record}",
        kind=kind,
        severity=severity,
        state="open",
        title=title,
        consequence=consequence,
        rule_version=RULE_VERSION,
        threshold=threshold,
        at_record=at_record,
        evidence=evidence,
        alternatives=alternatives,
        affected_conclusions=affected,
    )


def _lens(
    summary: RunSummary,
    records: tuple[SessionEvidenceRecord, ...],
    position_confidence: str,
) -> EvidenceLens:
    def last(form: str) -> SessionEvidenceRecord | None:
        return next(
            (record for record in reversed(records) if record.form == form),
            None,
        )

    wire = last("wire")
    parsed = last("parsed")
    rendered = last("rendered")
    believed = last("believed")
    return EvidenceLens(
        wire=_form("Retained wire evidence", wire),
        parsed=_form(
            f"Latest parsed state, position {position_confidence}",
            parsed,
        ),
        rendered=_form("Latest model-facing evidence", rendered),
        believed=_form("Agent's latest retained account", believed),
        truth=EvidenceForm(
            state="available",
            title="Verified experiment outcome",
            text=(
                "Objective satisfied."
                if summary.success
                else "Objective not satisfied by the verified predicate."
            ),
            citations=("benchmark:outcome",),
        ),
    )


def _form(title: str, record: SessionEvidenceRecord | None) -> EvidenceForm:
    if record is None:
        return EvidenceForm(
            state="missing",
            title=title,
            text="This evidence form was not retained.",
        )
    return EvidenceForm(
        state="available",
        title=title,
        text=record.preview,
        citations=(record.id,),
    )


def _agent_form(phase: str) -> str:
    if phase in {"plan", "response", "tool_call"}:
        return "believed"
    if phase in {"context", "tool_result", "prompt"}:
        return "rendered"
    return "parsed"


def _gateway_form(kind: str) -> str:
    if kind == "wire":
        return "wire"
    if kind in {"command", "tool_call"}:
        return "believed"
    return "parsed"


def _agent_status(row: dict[str, Any]) -> str:
    if row.get("error") or row.get("ok") is False:
        return "failed"
    if row.get("phase") in {"response", "tool_result", "turn_end"}:
        return "complete"
    return "unknown"


def _gateway_status(row: GatewayEvidenceRow) -> str:
    if row.kind == "tool_rejected" or row.payload.get("error"):
        return "failed"
    if row.kind in {"wire", "observation", "position", "tool_result"}:
        return "complete"
    return "unknown"


def _agent_label(phase: str, row: dict[str, Any]) -> str:
    if phase == "iteration":
        return f"Iteration {row.get('n', '?')}"
    if phase == "tool_call":
        return f"Call {row.get('name', 'unknown tool')}"
    if phase == "tool_result":
        return f"Result from {row.get('name', 'unknown tool')}"
    if phase == "response":
        return f"Model response, {row.get('stop_reason', 'unknown stop')}"
    return phase.replace("_", " ").title()


def _gateway_label(row: GatewayEvidenceRow) -> str:
    if row.kind == "command":
        return f"Command {row.payload.get('line', 'unknown')}"
    if row.kind == "observation":
        subject = row.payload.get("title") or row.payload.get("kind") or "state"
        return f"Observed {subject}"
    if row.kind == "position":
        return f"Position {row.payload.get('title', 'unknown')}"
    if row.kind in {"tool_call", "tool_result", "tool_rejected"}:
        return f"{row.kind.replace('_', ' ').title()}: {row.payload.get('tool', 'unknown')}"
    return row.kind.replace("_", " ").title()


def _room_id(row: GatewayEvidenceRow) -> str | None:
    if row.kind != "position":
        return None
    place = row.payload.get("place")
    return f"place:{place}" if isinstance(place, int) else None


def _agent_trace(row: dict[str, Any]) -> str | None:
    decoded = _decoded_result(row.get("result"))
    value = decoded.get("trace_id")
    return value if isinstance(value, str) else None


def _decoded_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return value if isinstance(value, dict) else {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _agent_tokens(row: dict[str, Any]) -> int:
    usage = row.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return (
        _usage_int(row, usage, "input_tokens", "fresh_input_tokens")
        + _usage_int(
            row,
            usage,
            "cache_read_tokens",
            "cache_read_input_tokens",
        )
        + _usage_int(
            row,
            usage,
            "cache_write_tokens",
            "cache_creation_input_tokens",
        )
        + _usage_int(row, usage, "output_tokens")
    )


def _usage_int(
    row: dict[str, Any],
    usage: dict[str, Any],
    *keys: str,
) -> int:
    for key in keys:
        value = usage.get(key, row.get(key))
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _preview(value: dict[str, Any]) -> str:
    for key in ("text", "task", "result", "line", "reason", "title"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:800]
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )[:800]


def _first_string(
    rows: tuple[dict[str, Any], ...],
    key: str,
) -> str | None:
    return next(
        (
            str(row[key])
            for row in rows
            if isinstance(row.get(key), str) and row[key]
        ),
        None,
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _player_id(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return "unattributed"


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
