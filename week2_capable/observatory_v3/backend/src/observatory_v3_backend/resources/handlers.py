"""Thin asynchronous handlers for bounded version 1 read resources."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..api_v1.contracts import (
    PlayerOption,
    ResourceChangeTarget,
    SessionCatalogItem,
    SessionCatalogResponse,
)
from ..experiment_jobs import ExperimentStore
from ..index import IndexStore
from ..materialization import (
    MaterializerBusyError,
    MaterializerClosedError,
    SessionMaterializer,
)
from ..materialization.models import MaterializationResult
from ..repositories import RegistryDatabase
from ..repositories.session_catalog import SessionCatalogRepository
from ..repositories.session_lookup import SessionLookupRepository
from ..sources.gateway_identity import ConfiguredPlayer
from ..storage_executor import StorageExecutor
from .bounds import bounded_text, content_identity
from .contracts import LivePartition, MaterializationPendingResponse
from .cursor import CursorCoordinates, InvalidCursorError, decode_cursor, encode_cursor
from .knowledge import KnowledgeResourceRepository
from .repository import (
    ResourceNotFoundError,
    ResourceRepository,
    ResourceUnavailableError,
)


class ReadResourceHandlers:
    """Coordinate demand materialization and off-loop bounded reads."""

    def __init__(
        self,
        *,
        index: IndexStore,
        registry: RegistryDatabase,
        materializer: SessionMaterializer,
        storage: StorageExecutor,
        knowledge: KnowledgeResourceRepository | None,
        experiment_store: ExperimentStore | None = None,
        configured_players: (
            Callable[[], tuple[ConfiguredPlayer, ...]] | None
        ) = None,
    ) -> None:
        self.index = index
        self.registry = registry
        self.materializer = materializer
        self.storage = storage
        self.resources = ResourceRepository(index, registry, experiment_store)
        self.knowledge = knowledge
        self._configured_players = configured_players
        self._pending_materializations: dict[
            str,
            asyncio.Task[MaterializationResult],
        ] = {}
        self._materialization_cleanups: dict[str, asyncio.Task[None]] = {}

    async def session_catalog(self, request: Request) -> JSONResponse:
        """Read one launcher catalog keyset without opening evidence journals."""
        limit = _limit(request, maximum=50, default=20)
        player_id = request.query_params.get("player_id")
        cursor = request.query_params.get("cursor")
        response = await self._session_catalog_value(
            limit=limit,
            player_id=player_id,
            cursor=cursor,
        )
        return _json(response)

    async def notification_catalog_target(self) -> ResourceChangeTarget:
        """Read the exact default catalog metadata used for fault publication."""
        response = await self._session_catalog_value(
            limit=20,
            player_id=None,
            cursor=None,
        )
        return ResourceChangeTarget(
            resource_kind="session_catalog",
            resource_id=response.resource_id,
            resource_version=response.resource_version,
            source_cursor=response.source_cursor,
        )

    async def _session_catalog_value(
        self,
        *,
        limit: int,
        player_id: str | None,
        cursor: str | None,
    ) -> SessionCatalogResponse:
        resource_id = f"session-catalog:{player_id or 'all'}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        page = await self.storage.run(
            SessionCatalogRepository(self.registry).keyset_page,
            after_created_at=None if after is None else after.primary,
            after_session_id=None if after is None else after.secondary,
            player_id=player_id,
            limit=limit + 1,
        )
        visible = page[:limit]
        sessions = []
        catalog_gaps: list[str] = []
        catalog_degraded = False
        for record in visible:
            retained_fault = await self.storage.run(
                self.index.materialization_fault,
                record.session_id,
            )
            pending = record.session_id in self._pending_materializations
            checkpoint = await self.storage.run(
                self.index.checkpoint,
                record.session_id,
            )
            projection_status: Literal["available", "pending", "fault"]
            projection_gaps: tuple[str, ...]
            if retained_fault is not None:
                projection_status = "fault"
                projection_gaps = ("capture_fault",)
                catalog_degraded = True
            elif pending:
                projection_status = "pending"
                projection_gaps = ("materialization_pending",)
            elif checkpoint is None:
                projection_status = "pending"
                projection_gaps = ("materialization_pending",)
            elif checkpoint.capture_status == "fault":
                projection_status = "fault"
                projection_gaps = checkpoint.capture_gaps or ("capture_fault",)
                catalog_degraded = True
            else:
                projection_status = "available"
                projection_gaps = checkpoint.capture_gaps
            character, character_truncated = bounded_text(
                record.character,
                max_bytes=512,
            )
            (
                objective,
                goal_count,
                nudge_count,
            ) = await self.storage.run(
                SessionCatalogRepository.objective_summary,
                record,
            )
            if objective is None and checkpoint is not None:
                objective = checkpoint.latest_goal
            objective_truncated = False
            if objective is not None:
                objective, objective_truncated = bounded_text(
                    objective,
                    max_bytes=512,
                )
            if character_truncated:
                projection_gaps = (
                    *projection_gaps,
                    "registry_character_truncated",
                )
            if objective_truncated:
                projection_gaps = (
                    *projection_gaps,
                    "registry_latest_goal_truncated",
                )
            catalog_gaps.extend(projection_gaps)
            event_count, latest_seq = await self.storage.run(
                SessionCatalogRepository.journal_summary,
                record,
            )
            sessions.append(
                SessionCatalogItem(
                    id=record.session_id,
                    player_id=record.player_id,
                    character=character,
                    gateway_session_id=record.gateway_session_id,
                    state=record.state,
                    control_state=None,
                    control_available=record.live,
                    capture_status=record.capture_status,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    ended_at=record.ended_at,
                    stop_mode=record.stop_mode,
                    projection_status=projection_status,
                    projection_gaps=projection_gaps[:16],
                    event_count=event_count,
                    turn_count=(
                        None if checkpoint is None else checkpoint.turn_count
                    ),
                    iteration_count=(
                        None if checkpoint is None else checkpoint.iteration_count
                    ),
                    latest_seq=latest_seq,
                    legacy=record.legacy,
                    live=record.live,
                    objective=objective,
                    goal_count=goal_count,
                    nudge_count=nudge_count,
                )
            )
        live_players = await self.storage.run(
            SessionCatalogRepository(self.registry).live_player_ids
        )
        configured = (
            await self.storage.run(self._configured_players)
            if self._configured_players is not None
            else ()
        )
        configured_ids = {player.id for player in configured}

        def _startable(player_id: str) -> bool:
            # Only a configured identity with no active session can be started.
            return player_id in configured_ids and player_id not in live_players

        options: dict[str, PlayerOption] = {}
        for item in sessions:
            options[item.player_id] = PlayerOption(
                id=item.player_id,
                label=item.character,
                start_available=_startable(item.player_id),
            )
        for player in configured:
            if player.id not in options:
                options[player.id] = PlayerOption(
                    id=player.id,
                    label=player.character,
                    start_available=_startable(player.id),
                )
        # Bounded to the SessionCatalogResponse.players contract limit.
        players = tuple(options.values())[:50]
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=visible[-1].created_at,
                    secondary=visible[-1].session_id,
                )
            )
            if len(page) > limit and visible
            else None
        )
        version, source_cursor = content_identity(
            "obc1",
            {
                "player_id": player_id,
                "sessions": [item.model_dump(mode="json") for item in sessions],
                "players": [player.model_dump(mode="json") for player in players],
            },
        )
        response = SessionCatalogResponse(
            resource_version=version,
            source_cursor=source_cursor,
            completeness=(
                "degraded"
                if catalog_degraded
                else ("partial" if catalog_gaps else "complete")
            ),
            continuation_cursor=continuation,
            capture_gaps=tuple(dict.fromkeys(catalog_gaps))[:32],
            source_refs=("registry.db sessions", "observatory index summaries"),
            players=players,
            sessions=tuple(sessions),
        )
        return response

    async def session_summary(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._ensure_materialized(session_id)
        if problem is not None:
            return problem
        return _json(await self.storage.run(self.resources.session_summary, session_id))

    async def _retire_materialization(
        self,
        session_id: str,
        task: asyncio.Task[MaterializationResult],
    ) -> None:
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except KeyError:
            pass
        except (MaterializerBusyError, MaterializerClosedError):
            pass
        except Exception:
            await self.storage.run(
                self.index.record_materialization_fault,
                session_id,
                "Selected-session materialization failed validation.",
            )
        else:
            if result.fault is None:
                await self.storage.run(
                    self.index.clear_materialization_fault,
                    session_id,
                )
            else:
                await self.storage.run(
                    self.index.record_materialization_fault,
                    session_id,
                    f"Selected-session materialization failed: {result.fault}.",
                )
        finally:
            cleanup = asyncio.current_task()
            if self._materialization_cleanups.get(session_id) is cleanup:
                self._materialization_cleanups.pop(session_id, None)
            if self._pending_materializations.get(session_id) is task:
                self._pending_materializations.pop(session_id, None)

    def _cleanup_finished(self, session_id: str, task: asyncio.Task[None]) -> None:
        if self._materialization_cleanups.get(session_id) is task:
            self._materialization_cleanups.pop(session_id, None)
        if not task.cancelled():
            task.exception()

    def _start_materialization(self, session_id: str) -> bool:
        if len(self._pending_materializations) >= self.materializer.capacity:
            return False
        task = asyncio.create_task(
            self.materializer.materialize(session_id),
            name=f"observatory-resource-demand:{session_id}",
        )
        self._pending_materializations[session_id] = task
        cleanup = asyncio.create_task(
            self._retire_materialization(session_id, task),
            name=f"observatory-resource-retire:{session_id}",
        )
        self._materialization_cleanups[session_id] = cleanup
        cleanup.add_done_callback(partial(self._cleanup_finished, session_id))
        return True

    async def close(self) -> None:
        """Drain bounded handler-owned completion bookkeeping."""
        cleanups = tuple(self._materialization_cleanups.values())
        if cleanups:
            await asyncio.gather(*cleanups, return_exceptions=True)

    async def goals(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._ensure_materialized(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.goal_page,
            session_id,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=20, default=20),
        )

    async def turns(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.turn_page,
            session_id,
            request.path_params["goal_id"],
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=20, default=20),
        )

    async def iterations(self, request: Request) -> JSONResponse:
        return await self._entity_page(
            request,
            "iterations",
            request.path_params["turn_id"],
        )

    async def evidence_children(self, request: Request) -> JSONResponse:
        return await self._entity_page(
            request,
            "children",
            request.path_params["record_id"],
        )

    async def evidence_record(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._ensure_materialized(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.evidence_record,
            session_id,
            request.path_params["record_id"],
        )

    async def evidence_content(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._ensure_materialized(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.evidence_content,
            session_id,
            request.path_params["record_id"],
            offset=_integer_query(
                request,
                "offset",
                minimum=0,
                maximum=2_147_483_647,
                default=0,
            ),
            max_bytes=_integer_query(
                request,
                "max_bytes",
                minimum=1,
                maximum=65_536,
                default=16_384,
            ),
        )

    async def lifecycle(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.lifecycle_page,
            session_id,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def lifecycle_content(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._ensure_materialized(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.lifecycle_content,
            session_id,
            int(request.path_params["sequence"]),
            offset=_integer_query(
                request,
                "offset",
                minimum=0,
                maximum=2_147_483_647,
                default=0,
            ),
            max_bytes=_integer_query(
                request,
                "max_bytes",
                minimum=1,
                maximum=65_536,
                default=16_384,
            ),
        )

    async def trace(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.trace_page,
            session_id,
            request.path_params["trace_id"],
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def wire_body(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.wire_body,
            session_id,
            request.path_params["digest"],
            max_bytes=_integer_query(
                request,
                "max_bytes",
                minimum=1,
                maximum=65_536,
                default=16_384,
            ),
        )

    async def map_prefix(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.map_prefix,
            session_id,
            cursor=request.query_params.get("cursor"),
        )

    async def cost_range(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.cost_range,
            session_id,
            scope_id=request.query_params.get("scope_id"),
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def search(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        query = request.query_params.get("q", "")
        if not 1 <= len(query) <= 500:
            return _error(
                "invalid_query",
                "q must contain between 1 and 500 characters",
                status=422,
            )
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.search_page,
            session_id,
            query=query,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=50, default=25),
        )

    async def live_partition(self, request: Request) -> JSONResponse:
        session_id = _session_id(request)
        partition = cast(LivePartition, request.path_params["partition"])
        if partition not in {
            "identity-lifecycle",
            "world-map",
            "position-path",
            "thought-activity",
            "vitals-combat",
            "economics",
            "controls",
            "diagnostics",
        }:
            return _error(
                "unknown_partition",
                "The requested Live partition is not published.",
                status=404,
            )
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.live_partition,
            session_id,
            partition,
        )

    async def experiment_catalog(self, request: Request) -> JSONResponse:
        return await self._read(
            self.resources.experiment_catalog,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=50, default=20),
        )

    async def experiment_detail(self, request: Request) -> JSONResponse:
        return await self._read(
            self.resources.experiment_detail,
            request.path_params["experiment_id"],
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def knowledge_summary(self, request: Request) -> JSONResponse:
        if self.knowledge is None:
            return _error(
                "source_unavailable",
                "The knowledge root is not configured.",
                503,
            )
        return await self._read(
            self.knowledge.summary,
            request.path_params["player_id"],
        )

    async def knowledge_detail(self, request: Request) -> JSONResponse:
        if self.knowledge is None:
            return _error(
                "source_unavailable",
                "The knowledge root is not configured.",
                503,
            )
        kind = request.path_params["kind"]
        if kind not in {"assertion", "change", "snapshot", "recovery"}:
            return _error(
                "not_found",
                "The requested knowledge layer is not published.",
                404,
            )
        return await self._read(
            self.knowledge.detail,
            request.path_params["player_id"],
            kind,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def knowledge_evidence(self, request: Request) -> JSONResponse:
        if self.knowledge is None:
            return _error(
                "source_unavailable",
                "The knowledge root is not configured.",
                503,
            )
        return await self._read(
            self.knowledge.evidence_page,
            request.path_params["player_id"],
            request.path_params["assertion_id"],
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def knowledge_assertion_content(self, request: Request) -> JSONResponse:
        if self.knowledge is None:
            return _error(
                "source_unavailable",
                "The knowledge root is not configured.",
                503,
            )
        return await self._read(
            self.knowledge.assertion_content,
            request.path_params["player_id"],
            request.path_params["assertion_id"],
            offset=_integer_query(
                request,
                "offset",
                minimum=0,
                maximum=2_147_483_647,
                default=0,
            ),
            max_bytes=_integer_query(
                request,
                "max_bytes",
                minimum=1,
                maximum=65_536,
                default=16_384,
            ),
        )

    async def _entity_page(
        self,
        request: Request,
        resource_kind: Literal["goals", "turns", "iterations", "children"],
        scope_id: str | None,
    ) -> JSONResponse:
        session_id = _session_id(request)
        problem = await self._materialize(session_id)
        if problem is not None:
            return problem
        return await self._read(
            self.resources.entity_page,
            session_id,
            resource_kind=resource_kind,
            scope_id=scope_id,
            cursor=request.query_params.get("cursor"),
            limit=_limit(request, maximum=100, default=50),
        )

    async def _materialize(self, session_id: str) -> JSONResponse | None:
        try:
            result = await self.materializer.materialize(session_id)
        except KeyError:
            return _error(
                "not_found",
                "The selected session does not exist.",
                status=404,
            )
        except (MaterializerBusyError, MaterializerClosedError):
            return _error(
                "source_unavailable",
                "Selected-session materialization is unavailable.",
                status=503,
            )
        if result.fault is not None:
            return _error(
                "capture_fault",
                f"Selected-session materialization failed: {result.fault}.",
                status=503,
            )
        # A successful pass resolves any fault an earlier attempt retained.
        retained = await self.storage.run(
            self.index.materialization_fault,
            session_id,
        )
        if retained is not None:
            await self.storage.run(
                self.index.clear_materialization_fault,
                session_id,
            )
        return None

    async def _ensure_materialized(self, session_id: str) -> JSONResponse | None:
        retained_fault = await self.storage.run(
            self.index.materialization_fault_record,
            session_id,
        )
        if retained_fault is not None:
            # A fault stays terminal only while the source is unchanged.
            # A session whose registry row or retained journals moved
            # after the fault earns a fresh attempt, which clears the
            # record when it succeeds.
            record = await self.storage.run(
                SessionLookupRepository(self.registry).get,
                session_id,
            )
            healed = await self.storage.run(self.index.checkpoint, session_id)
            retry = record is not None and (
                (healed is not None and healed.capture_status != "fault")
                or _advanced_since(record.updated_at, retained_fault[1])
                or await self.storage.run(
                    _journals_moved_since,
                    record.session_dir,
                    retained_fault[1],
                )
            )
            if not retry:
                return _error(
                    "capture_fault",
                    retained_fault[0],
                    status=503,
                )
        task = self._pending_materializations.get(session_id)
        if task is not None:
            if not task.done():
                return await self._pending(session_id)
            cleanup = self._materialization_cleanups.get(session_id)
            if cleanup is not None:
                await asyncio.shield(cleanup)
            return await self._ensure_materialized(session_id)

        checkpoint = await self.storage.run(self.index.checkpoint, session_id)
        if checkpoint is not None:
            return await self._materialize(session_id)
        record = await self.storage.run(
            SessionLookupRepository(self.registry).get,
            session_id,
        )
        if record is None:
            return _error(
                "not_found",
                "The selected session does not exist.",
                status=404,
            )
        if not self._start_materialization(session_id):
            return _error(
                "source_unavailable",
                "Selected-session materialization is at capacity.",
                status=503,
            )
        return await self._pending(session_id)

    async def _pending(self, session_id: str) -> JSONResponse:
        record = await self.storage.run(
            SessionLookupRepository(self.registry).get,
            session_id,
        )
        if record is None:
            return _error(
                "not_found",
                "The selected session does not exist.",
                status=404,
            )
        version, source_cursor = content_identity(
            "obp1",
            {
                "session_id": session_id,
                "updated_at": record.updated_at,
                "capture_status": record.capture_status,
            },
        )
        value = MaterializationPendingResponse(
            resource_id=f"session:{session_id}:materialization",
            resource_version=version,
            source_cursor=source_cursor,
            completeness="partial",
            capture_gaps=("materialization_pending",),
            source_refs=("registry.db sessions", "B4 selected-session materializer"),
            session_id=session_id,
            state="materialization_pending",
            retry_after_ms=50,
        )
        return _json(value, status=202, headers={"Retry-After": "0.05"})

    async def _read(
        self,
        function: Callable[..., BaseModel],
        *args: object,
        **kwargs: object,
    ) -> JSONResponse:
        try:
            value: BaseModel = await self.storage.run(function, *args, **kwargs)
        except ResourceNotFoundError:
            return _error("not_found", "The requested resource does not exist.", 404)
        except (ValueError, InvalidCursorError) as error:
            return _error("invalid_request", str(error), 422)
        except ResourceUnavailableError as error:
            return _error("source_unavailable", str(error), 503)
        return _json(value)


_RETAINED_JOURNAL_NAMES = (
    "gateway.db",
    "gateway.db-wal",
    "agent.jsonl",
    "operator-messages.json",
)


def _journals_moved_since(session_dir: Path, fault_recorded_at: str) -> bool:
    """Whether any retained journal was written after the fault landed."""
    try:
        threshold = datetime.fromisoformat(
            fault_recorded_at.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return True
    for name in _RETAINED_JOURNAL_NAMES:
        try:
            if (session_dir / name).stat().st_mtime > threshold:
                return True
        except OSError:
            continue
    return False


def _session_id(request: Request) -> str:
    return str(request.path_params["session_id"])


def _advanced_since(session_updated_at: str, fault_recorded_at: str) -> bool:
    """Whether the registry saw the session move after the fault landed."""
    try:
        session_stamp = datetime.fromisoformat(
            session_updated_at.replace("Z", "+00:00")
        )
        fault_stamp = datetime.fromisoformat(
            fault_recorded_at.replace("Z", "+00:00")
        )
    except ValueError:
        return True
    if session_stamp.tzinfo is None:
        session_stamp = session_stamp.replace(tzinfo=UTC)
    if fault_stamp.tzinfo is None:
        fault_stamp = fault_stamp.replace(tzinfo=UTC)
    return session_stamp > fault_stamp


def _limit(request: Request, *, maximum: int, default: int) -> int:
    return _integer_query(
        request,
        "limit",
        minimum=1,
        maximum=maximum,
        default=default,
    )


def _integer_query(
    request: Request,
    name: str,
    *,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _json(
    value: object,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    model_dump = getattr(value, "model_dump", None)
    if not callable(model_dump):
        raise TypeError("resource response must be a Pydantic model")
    return JSONResponse(
        model_dump(mode="json"),
        status_code=status,
        headers=headers,
    )


def _error(
    error: str,
    detail: str,
    status: int,
) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)
