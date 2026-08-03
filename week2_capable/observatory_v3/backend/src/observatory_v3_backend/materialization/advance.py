"""Synchronous selected-session advancement from committed native cursors."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from ..errors import MalformedSourceError
from ..index.identity import EntityKind, stable_entity_id
from ..index.models import (
    ExperimentCorrelation,
    HierarchyContext,
    IndexedEntity,
    SearchDocument,
    SessionCheckpoint,
    SessionIncrement,
    SessionProjection,
    SourceWatermark,
)
from ..index.projector import (
    IndexBuildError,
    SessionIndexProjector,
    _agent_search_text,
    _agent_title,
    _document,
    _entity,
    _experiment,
    _gateway_search_text,
    _positive_int,
    _sanitized_text,
    _source_identity,
)
from ..index.store import IndexStore
from ..models import GatewayEventRecord, LifecycleRecord, SessionRecord
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
    operator_transition_fault,
)
from .cursor import CompositeSourceCursor
from .models import AdvanceKind, AdvanceMetrics, MaterializationResult


class SourceIdentityFault(RuntimeError):
    """An append-only retained source changed identity or moved backwards."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IncrementalSessionAdvancer:
    """Advance one session without rereading its committed agent or gateway prefix."""

    def __init__(self, registry: RegistryDatabase, index: IndexStore) -> None:
        self.registry = registry
        self.index = index
        self.lookup = SessionLookupRepository(registry)
        self.bootstrap = SessionIndexProjector(registry, index)

    def advance(self, session_id: str) -> MaterializationResult:
        """Read and atomically commit the newest complete retained suffix."""
        checkpoint = self.index.checkpoint(session_id)
        if checkpoint is not None and _finalized(checkpoint):
            session = self.lookup.get(session_id)
            if session is not None and self._coordinates_current(
                session,
                checkpoint.watermark,
            ):
                return _result(
                    checkpoint,
                    kind="unchanged",
                    terminal=True,
                    metrics=_empty_metrics(checkpoint),
                )
        if checkpoint is None:
            session = self.lookup.get(session_id)
            if session is None:
                raise KeyError(f"unknown launcher session {session_id!r}")
            projection = self.bootstrap.project(session)
            return self._replace_projected_session(
                session,
                projection,
                kind="bootstrap",
            )
        if checkpoint.watermark.gateway_source_id == "unknown":
            session = self.lookup.get(session_id)
            if session is None:
                return self._fault(checkpoint, "session_source_missing")
            try:
                projection = self.bootstrap.project(session)
            except (MalformedSourceError, IndexBuildError):
                return self._fault(checkpoint, "malformed_source")
            return self._replace_projected_session(
                session,
                projection,
                kind="recovered",
            )
        try:
            return self._increment(checkpoint)
        except SourceIdentityFault as error:
            return self._fault(checkpoint, error.code)
        except (MalformedSourceError, IndexBuildError):
            return self._fault(checkpoint, "malformed_source")

    def _replace_projected_session(
        self,
        session: SessionRecord,
        projection: SessionProjection,
        *,
        kind: AdvanceKind,
    ) -> MaterializationResult:
        """Atomically replace one projection, then validate its live coordinates."""
        generation = self.index.replace_session(projection)
        committed = _required_checkpoint(self.index, session.session_id)
        post_commit_current = self._coordinates_current(
            session,
            committed.watermark,
        )
        metrics = projection.read_metrics
        return _result(
            committed,
            kind=kind,
            terminal=_finalized(committed) and post_commit_current,
            more_available=not post_commit_current,
            metrics=AdvanceMetrics(
                agent_start_offset=0,
                agent_records=metrics.agent_records,
                gateway_after_sequence=0,
                gateway_records=metrics.gateway_records,
                lifecycle_after_sequence=0,
                lifecycle_records=metrics.lifecycle_records,
            ),
            generation=generation,
        )

    def _increment(self, checkpoint: SessionCheckpoint) -> MaterializationResult:
        session = self.lookup.get(checkpoint.session_id)
        if session is None:
            return self._fault(checkpoint, "session_source_missing")
        watermark = checkpoint.watermark
        if session.gateway_session_id != watermark.gateway_session_id:
            raise SourceIdentityFault("gateway_session_identity_changed")

        agent_source = session.session_dir / "agent.jsonl"
        gateway_source = session.session_dir / "gateway.db"
        operator_source = session.session_dir / "operator-messages.json"
        agent_identity = _source_identity(agent_source)
        gateway_identity = _source_identity(gateway_source)
        operator_identity = _source_identity(operator_source)
        _validate_append_identity(
            previous=watermark.agent_source_id,
            current=agent_identity,
            position=watermark.agent_offset,
            changed_code="agent_source_replaced",
        )
        _validate_append_identity(
            previous=watermark.gateway_source_id,
            current=gateway_identity,
            position=watermark.gateway_sequence,
            changed_code="gateway_source_replaced",
        )
        if (
            agent_source.is_file()
            and agent_source.stat().st_size < watermark.agent_offset
        ):
            raise SourceIdentityFault("agent_source_truncated")

        agent_records, agent_offset, agent_next_line, incomplete_tail = _agent_suffix(
            session, watermark
        )
        gateway_records = _gateway_suffix(
            session,
            watermark,
            gateway_source=gateway_source,
        )
        lifecycle = _lifecycle_suffix(self.registry, session, watermark)
        if operator_identity == watermark.operator_source_id:
            operator_messages: tuple[dict[str, Any], ...] = ()
            operator_revision = watermark.operator_revision
            operator_message_count = watermark.operator_message_count
            operator_digest = watermark.operator_history_digest
            operator_state = watermark.operator_state
        else:
            operator = OperatorRepository(session).snapshot()
            operator_messages = operator.messages
            operator_revision = operator.revision
            if len(operator_messages) < watermark.operator_message_count:
                raise SourceIdentityFault("operator_snapshot_truncated")
            retained_prefix = operator_messages[: watermark.operator_message_count]
            if (
                operator_history_digest(retained_prefix)
                != watermark.operator_history_digest
            ):
                raise SourceIdentityFault("operator_snapshot_history_changed")
            transition_fault = operator_transition_fault(
                watermark.operator_state,
                operator_messages,
            )
            if transition_fault is not None:
                raise SourceIdentityFault(transition_fault)
            operator_message_count = len(operator_messages)
            operator_digest = operator_history_digest(operator_messages)
            operator_state = operator_application_state(operator_messages)
        _confirm_source_identity(
            agent_source,
            agent_identity,
            "agent_source_changed_during_read",
        )
        _confirm_source_identity(
            gateway_source,
            gateway_identity,
            "gateway_source_changed_during_read",
        )
        _confirm_source_identity(
            operator_source,
            operator_identity,
            "operator_source_changed_during_read",
        )
        experiment = _experiment(session)
        experiment_revision = _experiment_revision(experiment)
        if experiment_revision != watermark.experiment_revision:
            raise SourceIdentityFault("experiment_correlation_changed")
        lifecycle_sequence = (
            lifecycle[-1].sequence if lifecycle else watermark.lifecycle_sequence
        )
        gateway_sequence = (
            gateway_records[-1].sequence
            if gateway_records
            else watermark.gateway_sequence
        )
        next_watermark = SourceWatermark(
            registry_updated_at=session.updated_at,
            lifecycle_sequence=lifecycle_sequence,
            gateway_session_id=session.gateway_session_id,
            gateway_source_id=gateway_identity,
            gateway_sequence=gateway_sequence,
            agent_source_id=agent_identity,
            agent_offset=agent_offset,
            agent_next_line=agent_next_line,
            operator_source_id=operator_identity,
            operator_revision=operator_revision,
            operator_message_count=operator_message_count,
            operator_history_digest=operator_digest,
            operator_state=operator_state,
            experiment_revision=experiment_revision,
            knowledge_revision=watermark.knowledge_revision,
        )
        metrics = AdvanceMetrics(
            agent_start_offset=watermark.agent_offset,
            agent_records=len(agent_records),
            gateway_after_sequence=watermark.gateway_sequence,
            gateway_records=len(gateway_records),
            lifecycle_after_sequence=watermark.lifecycle_sequence,
            lifecycle_records=len(lifecycle),
        )
        page_was_full = (
            len(agent_records) == 1_000
            or len(gateway_records) == 2_000
            or len(lifecycle) == 1_000
        )
        coordinates_current = self._coordinates_current(
            session,
            next_watermark,
        )
        more_available = page_was_full or (
            not incomplete_tail and not coordinates_current
        )
        caught_up = not page_was_full and not incomplete_tail and coordinates_current
        committed_state = session.state if caught_up else checkpoint.state
        committed_ended_at = session.ended_at if caught_up else checkpoint.ended_at
        retained_partial_tail = "agent_incomplete_tail" in checkpoint.capture_gaps
        if (
            next_watermark == watermark
            and committed_state == checkpoint.state
            and session.capture_status == checkpoint.capture_status
            and committed_ended_at == checkpoint.ended_at
            and incomplete_tail == retained_partial_tail
        ):
            return _result(
                checkpoint,
                kind="unchanged",
                terminal=False,
                more_available=more_available,
                metrics=metrics,
            )

        context = self.index.hierarchy_context(session.session_id)
        projection = _incremental_projection(
            index=self.index,
            session=session,
            checkpoint=checkpoint,
            agent_records=agent_records,
            operator_messages=operator_messages,
            gateway_records=gateway_records,
            next_watermark=next_watermark,
            incomplete_tail=incomplete_tail,
            context=context,
            committed_state=committed_state,
            committed_ended_at=committed_ended_at,
        )
        if projection is None:
            generation = self.bootstrap.rebuild(session.session_id)
            recovered = _required_checkpoint(self.index, session.session_id)
            return _result(
                recovered,
                kind="recovered",
                terminal=_finalized(recovered),
                metrics=metrics,
                generation=generation,
            )
        generation = self.index.append_session(
            expected=watermark,
            increment=projection,
        )
        committed = _required_checkpoint(self.index, session.session_id)
        post_commit_current = self._coordinates_current(
            session,
            committed.watermark,
        )
        return _result(
            committed,
            kind="incremental",
            terminal=_finalized(committed) and post_commit_current,
            more_available=more_available or not post_commit_current,
            metrics=metrics,
            generation=generation,
        )

    def _coordinates_current(
        self,
        session: SessionRecord,
        watermark: SourceWatermark,
    ) -> bool:
        """Validate terminal source coordinates without rereading payloads."""
        current = self.lookup.get(session.session_id)
        if current is None:
            return False
        if (
            current.updated_at != watermark.registry_updated_at
            or current.state != session.state
            or current.ended_at != session.ended_at
            or current.capture_status != session.capture_status
            or current.gateway_session_id != watermark.gateway_session_id
            or _experiment_revision(_experiment(current))
            != watermark.experiment_revision
        ):
            return False
        agent_source = current.session_dir / "agent.jsonl"
        if _source_identity(agent_source) != watermark.agent_source_id:
            return False
        try:
            agent_size = agent_source.stat().st_size
        except FileNotFoundError:
            agent_size = 0
        if agent_size != watermark.agent_offset:
            return False
        gateway_source = current.session_dir / "gateway.db"
        if _source_identity(gateway_source) != watermark.gateway_source_id:
            return False
        if gateway_source.is_file():
            if EventRepository(current).latest_sequence() != watermark.gateway_sequence:
                return False
        elif watermark.gateway_sequence != 0:
            return False
        operator_source = current.session_dir / "operator-messages.json"
        if _source_identity(operator_source) != watermark.operator_source_id:
            return False
        return (
            LifecycleRepository(self.registry).latest_sequence(current.session_id)
            == watermark.lifecycle_sequence
        )

    def _fault(
        self,
        checkpoint: SessionCheckpoint,
        code: str,
    ) -> MaterializationResult:
        generation = self.index.record_capture_fault(
            checkpoint.session_id,
            code,
        )
        retained = _required_checkpoint(self.index, checkpoint.session_id)
        return _result(
            retained,
            kind="fault",
            terminal=_finalized(retained),
            fault=code,
            metrics=_empty_metrics(checkpoint),
            generation=generation,
        )


def _incremental_projection(
    *,
    index: IndexStore,
    session: SessionRecord,
    checkpoint: SessionCheckpoint,
    agent_records: tuple[dict[str, Any], ...],
    operator_messages: tuple[dict[str, Any], ...],
    gateway_records: tuple[GatewayEventRecord, ...],
    next_watermark: SourceWatermark,
    incomplete_tail: bool,
    context: HierarchyContext,
    committed_state: str,
    committed_ended_at: str | None,
) -> SessionIncrement | None:
    entities: list[IndexedEntity] = []
    documents: list[SearchDocument] = []
    logged_directives = {
        str(record["request_id"])
        for record in agent_records
        if record.get("phase") == "operator_control"
        and isinstance(record.get("request_id"), str)
    }
    agent_directive_anchors = tuple(
        f"operator:{record['request_id']}:{record['action']}"
        for record in agent_records
        if record.get("phase") == "operator_control"
        and isinstance(record.get("request_id"), str)
        and record.get("action") in {"guide", "revise"}
    )
    operator_anchors = tuple(
        dict.fromkeys(
            (
                *agent_directive_anchors,
                *(
                    f"operator:{message['request_id']}:{message['action']}"
                    for message in operator_messages
                    if message.get("applied_at") is not None
                ),
            )
        )
    )
    existing = index.entity_ids_for_anchors(session.session_id, operator_anchors)
    directives: dict[str, tuple[EntityKind, str]] = {}
    for agent_record in agent_records:
        request_value = agent_record.get("request_id")
        action_value = agent_record.get("action")
        if (
            agent_record.get("phase") != "operator_control"
            or not isinstance(request_value, str)
            or action_value not in {"guide", "revise"}
        ):
            continue
        agent_kind: EntityKind = "goal" if action_value == "revise" else "nudge"
        agent_anchor = f"operator:{request_value}:{action_value}"
        agent_entity_id = existing.get(agent_anchor)
        instruction_value = agent_record.get("instruction")
        if (
            agent_entity_id is None
            and agent_kind == "goal"
            and context.initial_goal_id is not None
            and context.initial_goal_title is not None
            and isinstance(instruction_value, str)
            and _sanitized_text(instruction_value) == context.initial_goal_title
        ):
            agent_entity_id = context.initial_goal_id
        if agent_entity_id is not None:
            directives[request_value] = (agent_kind, agent_entity_id)
    fallback_goals: list[tuple[str, int, str, str]] = []
    operator_active_goal = checkpoint.latest_goal_id
    latest_goal_id = checkpoint.latest_goal_id
    latest_goal = checkpoint.latest_goal
    for ordinal, message in enumerate(operator_messages, start=1):
        applied_iteration = message.get("applied_iteration")
        applied_at = message.get("applied_at")
        if applied_iteration is None and applied_at is None:
            continue
        if not isinstance(applied_iteration, int) or not isinstance(applied_at, str):
            raise IndexBuildError(
                f"operator request {message['request_id']!r} "
                "has a partial application boundary"
            )
        request_id = str(message["request_id"])
        action = str(message["action"])
        instruction = str(message["instruction"]).strip()
        kind: EntityKind = "goal" if action == "revise" else "nudge"
        anchor = f"operator:{request_id}:{action}"
        entity_id = existing.get(anchor)
        if (
            entity_id is None
            and kind == "goal"
            and applied_iteration == 0
            and request_id not in logged_directives
            and context.initial_goal_id is not None
            and _sanitized_text(instruction) == context.initial_goal_title
        ):
            entity_id = context.initial_goal_id
        if entity_id is not None:
            directives[request_id] = (kind, entity_id)
            if kind == "goal":
                operator_active_goal = entity_id
                latest_goal_id = entity_id
            continue
        if (
            context.last_agent_at is not None
            and request_id not in logged_directives
            and applied_at <= context.last_agent_at
        ):
            return None
        entity_id = stable_entity_id(session.session_id, kind, anchor)
        directives[request_id] = (kind, entity_id)
        if kind == "goal":
            operator_active_goal = entity_id
            latest_goal_id = entity_id
            latest_goal = _sanitized_text(instruction)
            fallback_goals.append((applied_at, ordinal, request_id, entity_id))
            parent_id = context.session_entity_id
            goal_id = entity_id
        else:
            if operator_active_goal is None:
                raise IndexBuildError(
                    f"operator request {request_id!r} has no active goal"
                )
            parent_id = operator_active_goal
            goal_id = operator_active_goal
        entity = _entity(
            session=session,
            kind=kind,
            anchor=anchor,
            parent_id=parent_id,
            goal_id=goal_id,
            turn_id=None,
            iteration_id=None,
            ordinal=1_000_000 + ordinal,
            occurred_at=applied_at,
            title=instruction,
            source_ref=f"operator-messages.json request {request_id}",
        )
        entities.append(entity)
        documents.append(_document(entity, instruction))

    scoped_goal_id = context.scoped_goal_id
    current_turn_id = context.current_turn_id
    current_iteration_id = context.current_iteration_id
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
    for agent_record in agent_records:
        line = _positive_int(agent_record.get("line"))
        phase = str(agent_record.get("phase") or "event")
        occurred_at = str(agent_record.get("at") or "")
        while (
            next_fallback is not None
            and occurred_at
            and next_fallback[0] <= occurred_at
        ):
            scoped_goal_id = next_fallback[3]
            next_fallback = next(pending_fallbacks, None)
        if phase == "operator_control":
            agent_request_id = agent_record.get("request_id")
            directive = (
                directives.get(agent_request_id)
                if isinstance(agent_request_id, str)
                else None
            )
            if directive is not None and directive[0] == "goal":
                scoped_goal_id = directive[1]
        if phase == "turn":
            anchor = f"agent:{line}"
            current_turn_id = stable_entity_id(
                session.session_id,
                "turn",
                anchor,
            )
            current_iteration_id = None
            turn = _entity(
                session=session,
                kind="turn",
                anchor=anchor,
                parent_id=scoped_goal_id or context.session_entity_id,
                goal_id=scoped_goal_id,
                turn_id=current_turn_id,
                iteration_id=None,
                ordinal=line,
                occurred_at=occurred_at,
                title=_agent_title(agent_record),
                source_ref=f"agent.jsonl line {line}",
            )
            entities.append(turn)
            documents.append(_document(turn, _agent_search_text(agent_record)))
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
                parent_id=(
                    current_turn_id or scoped_goal_id or context.session_entity_id
                ),
                goal_id=scoped_goal_id,
                turn_id=current_turn_id,
                iteration_id=current_iteration_id,
                ordinal=line,
                occurred_at=occurred_at,
                title=_agent_title(agent_record),
                source_ref=f"agent.jsonl line {line}",
            )
            entities.append(iteration)
        record_entity = _entity(
            session=session,
            kind="record",
            anchor=f"agent:{line}",
            parent_id=(
                current_iteration_id
                or current_turn_id
                or scoped_goal_id
                or context.session_entity_id
            ),
            goal_id=scoped_goal_id,
            turn_id=current_turn_id,
            iteration_id=current_iteration_id,
            ordinal=line,
            occurred_at=occurred_at,
            title=_agent_title(agent_record),
            source_ref=f"agent.jsonl line {line}",
        )
        entities.append(record_entity)
        text = _agent_search_text(agent_record)
        if text:
            documents.append(_document(record_entity, text))

    trace_anchors = tuple(
        f"gateway:{session.gateway_session_id}:trace:{record.trace_id}"
        for record in gateway_records
        if record.trace_id is not None
    )
    trace_ids = index.entity_ids_for_anchors(session.session_id, trace_anchors)
    for gateway in gateway_records:
        trace_entity_id: str | None = None
        if gateway.trace_id is not None:
            trace_anchor = (
                f"gateway:{session.gateway_session_id}:trace:{gateway.trace_id}"
            )
            trace_entity_id = trace_ids.get(trace_anchor)
            if trace_entity_id is None:
                trace = _entity(
                    session=session,
                    kind="trace",
                    anchor=trace_anchor,
                    parent_id=context.session_entity_id,
                    goal_id=None,
                    turn_id=None,
                    iteration_id=None,
                    ordinal=2_000_000 + gateway.sequence,
                    occurred_at=str(gateway.at),
                    title=f"Trace {gateway.trace_id}",
                    source_ref=f"gateway.db trace {gateway.trace_id}",
                )
                trace_entity_id = trace.id
                trace_ids[trace_anchor] = trace_entity_id
                entities.append(trace)
        gateway_entity = _entity(
            session=session,
            kind="record",
            anchor=(f"gateway:{session.gateway_session_id}:{gateway.sequence}"),
            parent_id=trace_entity_id or context.session_entity_id,
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

    gaps = [gap for gap in checkpoint.capture_gaps if gap != "agent_incomplete_tail"]
    if incomplete_tail:
        gaps.append("agent_incomplete_tail")
    return SessionIncrement(
        session_id=session.session_id,
        state=committed_state,
        updated_at=session.updated_at,
        ended_at=committed_ended_at,
        capture_status=session.capture_status,
        latest_goal_id=latest_goal_id,
        latest_goal=latest_goal,
        watermark=next_watermark,
        entities=tuple(entities),
        search_documents=tuple(documents),
        experiment=_experiment(session),
        capture_gaps=tuple(dict.fromkeys(gaps)),
    )


def _agent_suffix(
    session: SessionRecord,
    watermark: SourceWatermark,
) -> tuple[tuple[dict[str, Any], ...], int, int, bool]:
    page = AgentRepository(session).page(
        offset=watermark.agent_offset,
        start_line=watermark.agent_next_line,
        limit=1_000,
    )
    return (
        page.records,
        page.next_offset,
        page.next_line,
        page.incomplete_tail,
    )


def _gateway_suffix(
    session: SessionRecord,
    watermark: SourceWatermark,
    *,
    gateway_source: Path,
) -> tuple[GatewayEventRecord, ...]:
    if not gateway_source.is_file():
        if watermark.gateway_sequence:
            raise SourceIdentityFault("gateway_source_missing")
        return ()
    repository = EventRepository(session)
    latest = repository.latest_sequence()
    if latest < watermark.gateway_sequence:
        raise SourceIdentityFault("gateway_source_truncated")
    return repository.page(
        after=watermark.gateway_sequence,
        limit=2_000,
    )


def _lifecycle_suffix(
    registry: RegistryDatabase,
    session: SessionRecord,
    watermark: SourceWatermark,
) -> tuple[LifecycleRecord, ...]:
    repository = LifecycleRepository(registry)
    return repository.page(
        session.session_id,
        after=watermark.lifecycle_sequence,
        limit=1_000,
    )


def _validate_append_identity(
    *,
    previous: str,
    current: str,
    position: int,
    changed_code: str,
) -> None:
    if previous == current:
        return
    if previous == "missing" and position == 0:
        return
    raise SourceIdentityFault(changed_code)


def _confirm_source_identity(
    source: Path,
    expected: str,
    changed_code: str,
) -> None:
    if _source_identity(source) != expected:
        raise SourceIdentityFault(changed_code)


def _experiment_revision(
    experiment: ExperimentCorrelation | None,
) -> str | None:
    if experiment is None:
        return None
    return sha256(
        f"{experiment.experiment_id}\0{experiment.run_id}".encode()
    ).hexdigest()


def _required_checkpoint(index: IndexStore, session_id: str) -> SessionCheckpoint:
    checkpoint = index.checkpoint(session_id)
    if checkpoint is None:
        raise RuntimeError(f"session {session_id!r} was not committed")
    return checkpoint


def _empty_metrics(checkpoint: SessionCheckpoint) -> AdvanceMetrics:
    return AdvanceMetrics(
        agent_start_offset=checkpoint.watermark.agent_offset,
        agent_records=0,
        gateway_after_sequence=checkpoint.watermark.gateway_sequence,
        gateway_records=0,
        lifecycle_after_sequence=checkpoint.watermark.lifecycle_sequence,
        lifecycle_records=0,
    )


def _result(
    checkpoint: SessionCheckpoint,
    *,
    kind: AdvanceKind,
    terminal: bool,
    more_available: bool = False,
    metrics: AdvanceMetrics,
    generation: int | None = None,
    fault: str | None = None,
) -> MaterializationResult:
    return MaterializationResult(
        session_id=checkpoint.session_id,
        cursor=CompositeSourceCursor.from_watermark(checkpoint.watermark).token,
        generation=checkpoint.generation if generation is None else generation,
        kind=kind,
        terminal=terminal,
        more_available=more_available,
        fault=fault,
        metrics=metrics,
    )


def _terminal(state: str) -> bool:
    return state not in {"starting", "running", "draining", "quarantined"}


def _finalized(checkpoint: SessionCheckpoint) -> bool:
    return _terminal(checkpoint.state) and (
        "agent_incomplete_tail" not in checkpoint.capture_gaps
    )
