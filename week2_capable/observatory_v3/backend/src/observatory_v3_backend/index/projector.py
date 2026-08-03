"""Explicit selected-session rebuild into deterministic logical index rows."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..models import GatewayEventRecord, SessionRecord
from ..redaction import sanitize_evidence
from ..repositories import (
    AgentRepository,
    EventRepository,
    LifecycleRepository,
    OperatorRepository,
    RegistryDatabase,
    SessionLookupRepository,
)
from ..repositories.operator import (
    operator_application_state,
    operator_history_digest,
)
from .identity import EntityKind, stable_entity_id
from .models import (
    ExperimentCorrelation,
    IndexedEntity,
    ProjectionReadMetrics,
    SearchDocument,
    SessionProjection,
    SourceWatermark,
)
from .store import IndexStore

MAX_SEARCH_BYTES = 16 * 1024
AGENT_SEARCH_FIELDS = (
    "instruction",
    "text",
    "task",
    "stop_reason",
    "model",
    "name",
    "args",
    "result",
)
GATEWAY_SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "command": ("line",),
    "poll": ("text",),
    "unsolicited": ("text",),
    "parser_input": ("text",),
    "wire_text": ("text",),
    "observation": (
        "text",
        "title",
        "description",
        "exits",
        "mobs",
        "objects",
    ),
    "unparsed": (
        "text",
        "title",
        "description",
        "exits",
        "mobs",
        "objects",
    ),
    "tool_call": ("tool", "capability"),
    "tool_result": ("tool", "capability"),
    "observer_probe": ("command", "reason"),
    "capability_gap": ("line", "reason"),
}


class IndexBuildError(RuntimeError):
    """Retained evidence cannot produce one coherent indexed generation."""


class SessionIndexProjector:
    """Build and atomically replace one selected launcher session."""

    def __init__(self, registry: RegistryDatabase, index: IndexStore) -> None:
        self.registry = registry
        self.index = index
        self.lookup = SessionLookupRepository(registry)

    def rebuild(self, session_id: str) -> int:
        """Explicitly rebuild one session without enumerating other sessions."""
        session = self.lookup.get(session_id)
        if session is None:
            raise KeyError(f"unknown launcher session {session_id!r}")
        projection = self.project(session)
        return self.index.replace_session(projection)

    def project(self, session: SessionRecord) -> SessionProjection:
        """Prepare a complete logical replacement before opening a write."""
        agent_source = session.session_dir / "agent.jsonl"
        gateway_source = session.session_dir / "gateway.db"
        operator_source = session.session_dir / "operator-messages.json"
        agent_source_id = _source_identity(agent_source)
        gateway_source_id = _source_identity(gateway_source)
        operator_source_id = _source_identity(operator_source)
        agent_records, agent_offset, agent_next_line, incomplete_tail = (
            self._agent_records(session)
        )
        operator = OperatorRepository(session).snapshot()
        gateway_records = self._gateway_records(session)
        lifecycle_sequence, lifecycle_records = self._lifecycle_position(
            session.session_id
        )
        _confirm_projection_source(agent_source, agent_source_id, "agent")
        _confirm_projection_source(gateway_source, gateway_source_id, "gateway")
        _confirm_projection_source(operator_source, operator_source_id, "operator")
        entities, documents, latest_goal_id, latest_goal, gaps = _entities(
            session,
            agent_records,
            operator.messages,
            gateway_records,
        )
        if incomplete_tail:
            gaps.append("agent_incomplete_tail")
        experiment = _experiment(session)
        watermark = SourceWatermark(
            registry_updated_at=session.updated_at,
            lifecycle_sequence=lifecycle_sequence,
            gateway_session_id=session.gateway_session_id,
            gateway_source_id=gateway_source_id,
            gateway_sequence=(gateway_records[-1].sequence if gateway_records else 0),
            agent_source_id=agent_source_id,
            agent_offset=agent_offset,
            agent_next_line=agent_next_line,
            operator_source_id=operator_source_id,
            operator_revision=operator.revision,
            operator_message_count=len(operator.messages),
            operator_history_digest=operator_history_digest(operator.messages),
            operator_state=operator_application_state(operator.messages),
            experiment_revision=(
                None
                if experiment is None
                else sha256(
                    f"{experiment.experiment_id}\0{experiment.run_id}".encode()
                ).hexdigest()
            ),
            knowledge_revision=None,
        )
        return SessionProjection(
            session_id=session.session_id,
            player_id=session.player_id,
            character=session.character,
            state=session.state,
            created_at=session.created_at,
            updated_at=session.updated_at,
            ended_at=session.ended_at,
            capture_status=session.capture_status,
            latest_goal_id=latest_goal_id,
            latest_goal=latest_goal,
            goal_count=sum(entity.kind == "goal" for entity in entities),
            nudge_count=sum(entity.kind == "nudge" for entity in entities),
            turn_count=sum(entity.kind == "turn" for entity in entities),
            iteration_count=sum(entity.kind == "iteration" for entity in entities),
            record_count=sum(entity.kind == "record" for entity in entities),
            watermark=watermark,
            entities=entities,
            search_documents=documents,
            experiment=experiment,
            capture_gaps=tuple(dict.fromkeys(gaps)),
            read_metrics=ProjectionReadMetrics(
                agent_records=len(agent_records),
                gateway_records=len(gateway_records),
                lifecycle_records=lifecycle_records,
            ),
        )

    @staticmethod
    def _agent_records(
        session: SessionRecord,
    ) -> tuple[tuple[dict[str, Any], ...], int, int, bool]:
        repository = AgentRepository(session)
        records: list[dict[str, Any]] = []
        offset = 0
        line = 1
        incomplete_tail = False
        while True:
            page = repository.page(
                offset=offset,
                start_line=line,
                limit=250,
            )
            records.extend(page.records)
            offset = page.next_offset
            line = page.next_line
            incomplete_tail = page.incomplete_tail
            if len(page.records) < 250 or page.incomplete_tail:
                break
        return tuple(records), offset, line, incomplete_tail

    @staticmethod
    def _gateway_records(
        session: SessionRecord,
    ) -> tuple[GatewayEventRecord, ...]:
        source = session.session_dir / "gateway.db"
        if not source.is_file():
            return ()
        repository = EventRepository(session)
        records: list[GatewayEventRecord] = []
        after = 0
        while True:
            page = repository.page(after=after, limit=500)
            records.extend(page)
            if len(page) < 500:
                break
            after = page[-1].sequence
        return tuple(records)

    def _lifecycle_position(self, session_id: str) -> tuple[int, int]:
        repository = LifecycleRepository(self.registry)
        after = 0
        count = 0
        while True:
            page = repository.page(session_id, after=after, limit=250)
            if not page:
                return after, count
            count += len(page)
            after = page[-1].sequence
            if len(page) < 250:
                return after, count


def _entities(
    session: SessionRecord,
    agent_records: tuple[dict[str, Any], ...],
    operator_messages: tuple[dict[str, Any], ...],
    gateway_records: tuple[GatewayEventRecord, ...],
) -> tuple[
    tuple[IndexedEntity, ...],
    tuple[SearchDocument, ...],
    str | None,
    str | None,
    list[str],
]:
    entities: list[IndexedEntity] = []
    documents: list[SearchDocument] = []
    gaps: list[str] = []
    session_entity_id = stable_entity_id(
        session.session_id,
        "session",
        f"registry:{session.session_id}",
    )
    entities.append(
        _entity(
            session=session,
            kind="session",
            anchor=f"registry:{session.session_id}",
            parent_id=None,
            goal_id=None,
            turn_id=None,
            iteration_id=None,
            ordinal=0,
            occurred_at=session.created_at,
            title=f"{session.character} session",
            source_ref="registry.db sessions",
        )
    )
    initial = _initial_goal(agent_records)
    active_goal_id: str | None = None
    latest_goal: str | None = None
    if initial is not None:
        line, title, at = initial
        anchor = f"agent:{line}:initial"
        active_goal_id = stable_entity_id(session.session_id, "goal", anchor)
        goal = _entity(
            session=session,
            kind="goal",
            anchor=anchor,
            parent_id=session_entity_id,
            goal_id=active_goal_id,
            turn_id=None,
            iteration_id=None,
            ordinal=line,
            occurred_at=at,
            title=title,
            source_ref=f"agent.jsonl line {line}",
        )
        latest_goal = goal.title
        entities.append(goal)
        documents.append(_document(goal, title))

    logged_directives = {
        str(record.get("request_id"))
        for record in agent_records
        if record.get("phase") == "operator_control"
        and isinstance(record.get("request_id"), str)
    }
    directives: dict[str, tuple[EntityKind, str]] = {}
    fallback_goals: list[tuple[str, int, str, str]] = []
    seen_requests: set[str] = set()
    for index, message in enumerate(operator_messages, start=1):
        request_id = str(message["request_id"])
        if request_id in seen_requests:
            continue
        seen_requests.add(request_id)
        applied_iteration = message.get("applied_iteration")
        applied_at = message.get("applied_at")
        if applied_iteration is None and applied_at is None:
            continue
        if not isinstance(applied_iteration, int) or not isinstance(applied_at, str):
            raise IndexBuildError(
                f"operator request {request_id!r} has a partial application boundary"
            )
        action = str(message["action"])
        instruction = str(message["instruction"]).strip()
        kind: EntityKind = "goal" if action == "revise" else "nudge"
        anchor = f"operator:{request_id}:{action}"
        entity_id = stable_entity_id(session.session_id, kind, anchor)
        if (
            kind == "goal"
            and initial is not None
            and applied_iteration == 0
            and request_id not in logged_directives
            and instruction == initial[1]
        ):
            assert active_goal_id is not None
            directives[request_id] = ("goal", active_goal_id)
            latest_goal = _sanitized_text(instruction)
            continue
        directives[request_id] = (kind, entity_id)
        if kind == "goal":
            active_goal_id = entity_id
            latest_goal = _sanitized_text(instruction)
            fallback_goals.append((applied_at, index, request_id, entity_id))
            parent_id = session_entity_id
            goal_id = entity_id
        else:
            if active_goal_id is None:
                gaps.append(f"nudge_without_goal:{request_id}")
                continue
            parent_id = active_goal_id
            goal_id = active_goal_id
        entity = _entity(
            session=session,
            kind=kind,
            anchor=anchor,
            parent_id=parent_id,
            goal_id=goal_id,
            turn_id=None,
            iteration_id=None,
            ordinal=1_000_000 + index,
            occurred_at=applied_at,
            title=instruction,
            source_ref=f"operator-messages.json request {request_id}",
        )
        entities.append(entity)
        documents.append(_document(entity, instruction))

    current_turn_id: str | None = None
    current_iteration_id: str | None = None
    scoped_goal_id = (
        stable_entity_id(session.session_id, "goal", f"agent:{initial[0]}:initial")
        if initial is not None
        else None
    )
    pending_fallbacks = iter(
        sorted(
            (
                boundary
                for boundary in fallback_goals
                if boundary[2] not in logged_directives
            ),
            key=lambda item: (item[0], item[1]),
        )
    )
    next_fallback = next(pending_fallbacks, None)
    for record in agent_records:
        line = _positive_int(record.get("line"))
        phase = str(record.get("phase") or "event")
        occurred_at = str(record.get("at") or "")
        while (
            next_fallback is not None
            and occurred_at
            and next_fallback[0] <= occurred_at
        ):
            scoped_goal_id = next_fallback[3]
            next_fallback = next(pending_fallbacks, None)
        if phase == "operator_control":
            control_request_id = record.get("request_id")
            directive = (
                directives.get(control_request_id)
                if isinstance(control_request_id, str)
                else None
            )
            if directive is not None and directive[0] == "goal":
                scoped_goal_id = directive[1]
        if phase == "turn":
            anchor = f"agent:{line}"
            current_turn_id = stable_entity_id(session.session_id, "turn", anchor)
            current_iteration_id = None
            turn = _entity(
                session=session,
                kind="turn",
                anchor=anchor,
                parent_id=scoped_goal_id or session_entity_id,
                goal_id=scoped_goal_id,
                turn_id=current_turn_id,
                iteration_id=None,
                ordinal=line,
                occurred_at=occurred_at,
                title=_agent_title(record),
                source_ref=f"agent.jsonl line {line}",
            )
            entities.append(turn)
            documents.append(_document(turn, _agent_search_text(record)))
        elif phase == "iteration":
            anchor = f"agent:{line}"
            current_iteration_id = stable_entity_id(
                session.session_id,
                "iteration",
                anchor,
            )
            iteration = _entity(
                session=session,
                kind="iteration",
                anchor=anchor,
                parent_id=current_turn_id or scoped_goal_id or session_entity_id,
                goal_id=scoped_goal_id,
                turn_id=current_turn_id,
                iteration_id=current_iteration_id,
                ordinal=line,
                occurred_at=occurred_at,
                title=_agent_title(record),
                source_ref=f"agent.jsonl line {line}",
            )
            entities.append(iteration)
        record_anchor = f"agent:{line}"
        record_entity = _entity(
            session=session,
            kind="record",
            anchor=record_anchor,
            parent_id=(
                current_iteration_id
                or current_turn_id
                or scoped_goal_id
                or session_entity_id
            ),
            goal_id=scoped_goal_id,
            turn_id=current_turn_id,
            iteration_id=current_iteration_id,
            ordinal=line,
            occurred_at=occurred_at,
            title=_agent_title(record),
            source_ref=f"agent.jsonl line {line}",
        )
        entities.append(record_entity)
        text = _agent_search_text(record)
        if text:
            documents.append(_document(record_entity, text))

    trace_ids: dict[str, str] = {}
    for gateway in gateway_records:
        trace_entity_id: str | None = None
        if gateway.trace_id is not None:
            trace_anchor = (
                f"gateway:{session.gateway_session_id}:trace:{gateway.trace_id}"
            )
            trace_entity_id = trace_ids.get(gateway.trace_id)
            if trace_entity_id is None:
                trace_entity = _entity(
                    session=session,
                    kind="trace",
                    anchor=trace_anchor,
                    parent_id=session_entity_id,
                    goal_id=None,
                    turn_id=None,
                    iteration_id=None,
                    ordinal=2_000_000 + gateway.sequence,
                    occurred_at=str(gateway.at),
                    title=f"Trace {gateway.trace_id}",
                    source_ref=f"gateway.db trace {gateway.trace_id}",
                )
                trace_entity_id = trace_entity.id
                trace_ids[gateway.trace_id] = trace_entity_id
                entities.append(trace_entity)
        anchor = f"gateway:{session.gateway_session_id}:{gateway.sequence}"
        gateway_entity = _entity(
            session=session,
            kind="record",
            anchor=anchor,
            parent_id=trace_entity_id or session_entity_id,
            goal_id=None,
            turn_id=None,
            iteration_id=None,
            ordinal=3_000_000 + gateway.sequence,
            occurred_at=str(gateway.at),
            title=gateway.kind.replace("_", " ").title(),
            source_ref=f"gateway.db event {gateway.sequence}",
        )
        entities.append(gateway_entity)
        text = _gateway_search_text(gateway)
        if text:
            documents.append(_document(gateway_entity, text))

    return (
        tuple(entities),
        tuple(documents),
        active_goal_id,
        latest_goal,
        gaps,
    )


def _entity(
    *,
    session: SessionRecord,
    kind: EntityKind,
    anchor: str,
    parent_id: str | None,
    goal_id: str | None,
    turn_id: str | None,
    iteration_id: str | None,
    ordinal: int,
    occurred_at: str,
    title: str,
    source_ref: str,
) -> IndexedEntity:
    return IndexedEntity(
        id=stable_entity_id(session.session_id, kind, anchor),
        session_id=session.session_id,
        player_id=session.player_id,
        kind=kind,
        source_anchor=anchor,
        parent_id=parent_id,
        goal_id=goal_id,
        turn_id=turn_id,
        iteration_id=iteration_id,
        ordinal=ordinal,
        occurred_at=occurred_at,
        title=_sanitized_text(title),
        source_ref=source_ref,
    )


def _document(entity: IndexedEntity, body: str) -> SearchDocument:
    return SearchDocument(
        entity_id=entity.id,
        session_id=entity.session_id,
        player_id=entity.player_id,
        kind=entity.kind,
        occurred_at=entity.occurred_at,
        title=_sanitized_text(entity.title),
        body=_sanitized_text(body),
    )


def _initial_goal(
    records: tuple[dict[str, Any], ...],
) -> tuple[int, str, str] | None:
    for record in records:
        if record.get("phase") != "session_start":
            continue
        objective = record.get("objective")
        if isinstance(objective, dict):
            title = objective.get("title")
            if isinstance(title, str) and title.strip():
                return (
                    _positive_int(record.get("line")),
                    title.strip(),
                    str(record.get("at") or ""),
                )
    for record in records:
        instruction = record.get("instruction")
        if record.get("phase") == "turn" and isinstance(instruction, str):
            if instruction.strip():
                return (
                    _positive_int(record.get("line")),
                    instruction.strip(),
                    str(record.get("at") or ""),
                )
    return None


def _agent_title(record: dict[str, Any]) -> str:
    phase = str(record.get("phase") or "event")
    number = record.get("n")
    if phase in {"turn", "iteration"} and isinstance(number, int):
        return f"{phase.title()} {number}"
    model = record.get("model")
    if isinstance(model, str) and model:
        return f"{phase.replace('_', ' ').title()} · {model}"
    return phase.replace("_", " ").title()


def _agent_search_text(record: dict[str, Any]) -> str:
    values: list[object] = []
    objective = record.get("objective")
    if isinstance(objective, dict) and "title" in objective:
        values.append(objective["title"])
    values.extend(record[field] for field in AGENT_SEARCH_FIELDS if field in record)
    return _search_values(values)


def _gateway_search_text(record: GatewayEventRecord) -> str:
    fields = GATEWAY_SEARCH_FIELDS.get(record.kind)
    if fields is None:
        return ""
    if record.kind == "wire_text" and record.payload.get("redacted") is not False:
        return ""
    return _search_values(
        [record.payload[field] for field in fields if field in record.payload]
    )


def _search_values(values: list[object]) -> str:
    parts: list[str] = []
    for value in values:
        sanitized = sanitize_evidence(value)
        if isinstance(sanitized, str):
            text = sanitized
        elif isinstance(sanitized, list | dict):
            text = json.dumps(
                sanitized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        elif sanitized is None:
            continue
        else:
            text = str(sanitized)
        if text.strip():
            parts.append(text.strip())
    return _bounded_text(" ".join(parts))


def _bounded_text(value: str) -> str:
    encoded = value.encode("utf-8")[:MAX_SEARCH_BYTES]
    return encoded.decode("utf-8", errors="ignore")


def _sanitized_text(value: str) -> str:
    sanitized = sanitize_evidence(value)
    return _bounded_text(sanitized if isinstance(sanitized, str) else "")


def _experiment(session: SessionRecord) -> ExperimentCorrelation | None:
    if session.experiment_id is None and session.run_id is None:
        return None
    if session.experiment_id is None or session.run_id is None:
        return None
    anchor = f"experiment:{session.experiment_id}:run:{session.run_id}"
    return ExperimentCorrelation(
        id=stable_entity_id(session.session_id, "experiment_sample", anchor),
        experiment_id=session.experiment_id,
        run_id=session.run_id,
        session_id=session.session_id,
    )


def _source_identity(source: Path) -> str:
    try:
        stat = source.stat()
    except FileNotFoundError:
        return "missing"
    return f"{stat.st_dev}:{stat.st_ino}"


def _confirm_projection_source(
    source: Path,
    expected: str,
    label: str,
) -> None:
    if _source_identity(source) != expected:
        raise IndexBuildError(f"{label}_source_changed_during_projection")


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or value < 1:
        raise IndexBuildError("retained agent line must be a positive integer")
    return value
