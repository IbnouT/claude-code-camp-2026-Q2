"""Local read API and static host for the Boukensha observatory."""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from mud_gateway.contracts import contract_schemas
from mud_gateway.stream import serialize_event
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route

from .api_v1 import api_v1_routes, openapi_document
from .api_v1.contracts import ApiError
from .capabilities import discover
from .contracts import (
    AskRequest,
    ExperimentForkRequest,
    ExperimentRunRequest,
    ExperimentValidateRequest,
    IncidentExportRequest,
    LiveControlRequest,
    LiveVoiceRequest,
    ObservatoryQuery,
    RuntimeSessionWireEvidence,
)
from .execution import ExperimentExecutor, ExperimentRequestConflict
from .experiment_catalog import experiment_registry, experiment_scenarios
from .experiments import fork_one_variable, sample_queue, validate_definition
from .incidents import build_capsule
from .index import IndexStore
from .knowledge_contracts import KnowledgeRecoveryRequest
from .projections.history import diagnostic_history
from .projections.knowledge import project_knowledge
from .projections.session import (
    project_recorded_session,
    project_recorded_session_prefix,
)
from .queries import answer
from .queries.model import ModelTranslator
from .runtime_views import RuntimeReadService
from .settings import Settings
from .sources.atlas import AtlasSource
from .sources.benchmark import BenchmarkSource
from .sources.comparison import rendering_comparison
from .sources.gateway import GatewaySource
from .sources.knowledge import KnowledgeSource, KnowledgeSourceError
from .sources.recorded_session import RecordedSessionSource
from .sources.runtime import RuntimeSource, RuntimeSourceError
from .sources.sector_overrides import DEFAULT_OVERRIDE_PATH
from .storage_executor import StorageExecutor
from .voice import (
    VoiceService,
    VoiceSynthesisError,
    VoiceUnavailableError,
)


def create_app(
    settings: Settings | None = None,
    *,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
    copilot_transport: httpx.AsyncBaseTransport | None = None,
    voice_transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    active = settings or Settings.from_environment()
    gateway = GatewaySource(
        active.gateway_url,
        transport=gateway_transport,
    )
    runtime = (
        None if active.runtime_root is None else RuntimeSource(active.runtime_root)
    )
    storage = StorageExecutor(capacity=8)
    knowledge_source = (
        None if active.runtime_root is None else KnowledgeSource(active.runtime_root)
    )
    benchmark = (
        BenchmarkSource(active.benchmark_root)
        if active.benchmark_root is not None
        else None
    )
    recorded_sessions = (
        RecordedSessionSource(active.benchmark_root)
        if active.benchmark_root is not None
        else None
    )
    atlas = AtlasSource(
        active.world_root,
        override_path=(
            DEFAULT_OVERRIDE_PATH
            if os.environ.get("OBSERVATORY_ENABLE_SECTOR_OVERRIDES") == "1"
            else None
        ),
    )
    runtime_reads = (
        None if runtime is None else RuntimeReadService(runtime=runtime, atlas=atlas)
    )
    experiment_executor = (
        ExperimentExecutor(
            active.experiment_state_root,
            benchmark_root=active.benchmark_root,
            storage=storage,
        )
        if (
            active.experiment_state_root is not None
            and active.benchmark_root is not None
        )
        else None
    )
    model_spend = 0.0
    translator = (
        ModelTranslator(
            endpoint=active.copilot_endpoint,
            api_key=active.copilot_api_key,
            model=active.copilot_model,
            input_rate=active.copilot_input_rate,
            output_rate=active.copilot_output_rate,
            transport=copilot_transport,
        )
        if (
            active.copilot_model
            and active.copilot_api_key
            and active.copilot_spend_cap > 0
            and active.copilot_input_rate > 0
            and active.copilot_output_rate > 0
        )
        else None
    )
    voice = VoiceService(
        endpoint=active.voice_endpoint,
        api_key=(
            active.voice_api_key
            if "live-voice" not in active.disabled_features
            else None
        ),
        model=active.voice_model,
        voice=active.voice_name,
        cache_root=active.voice_cache_root,
        transport=voice_transport,
    )

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "evidence_plane": "read_only",
                "control_plane": "authenticated_local",
            }
        )

    async def capabilities(_request: Request) -> JSONResponse:
        result = await discover(
            active,
            gateway_transport=gateway_transport,
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def sessions(_request: Request) -> JSONResponse:
        if runtime is not None and runtime.available:
            try:
                available = await storage.run(runtime.sessions)
            except RuntimeSourceError as error:
                return _runtime_error(error)
            players: dict[str, dict[str, str]] = {}
            for session in available:
                players.setdefault(
                    session.player_id,
                    {
                        "id": session.player_id,
                        "label": session.character,
                    },
                )
            return JSONResponse(
                {
                    "version": 1,
                    "players": list(players.values()),
                    "sessions": [session.public() for session in available],
                }
            )
        try:
            payload = await gateway.sessions()
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)
        fallback = [
            {
                "id": session,
                "player_id": "legacy",
                "character": "Legacy gateway",
                "gateway_session_id": session,
                "state": "unknown",
                "control_state": None,
                "control_available": False,
                "capture_status": "unknown",
                "created_at": "",
                "updated_at": "",
                "ended_at": None,
                "event_count": 0,
                "latest_seq": 0,
                "legacy": True,
                "live": True,
            }
            for session in payload["sessions"]
        ]
        return JSONResponse(
            {
                "version": 1,
                "players": [{"id": "legacy", "label": "Legacy gateway"}],
                "sessions": fallback,
            }
        )

    async def contracts(_request: Request) -> JSONResponse:
        if runtime is not None and runtime.available:
            return JSONResponse(contract_schemas())
        try:
            return JSONResponse(await gateway.json("/contracts"))
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

    async def gateway_events(request: Request) -> Response:
        session = request.path_params["session"]
        endpoint = request.path_params.get("endpoint", "events")
        if endpoint not in {"events", "replay"}:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if runtime is not None and runtime.available:
            try:
                selected = await storage.run(runtime.session, session)
            except RuntimeSourceError as error:
                return _runtime_error(error)
            if selected is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            return _runtime_events(
                request,
                runtime,
                storage,
                selected.id,
                endpoint,
            )
        query = list(request.query_params.multi_items())
        context = gateway.stream(
            f"/sessions/{session}/{endpoint}",
            query=query,
        )
        try:
            upstream = await context.__aenter__()
        except (httpx.HTTPError, ValueError) as error:
            return _upstream_error(error)

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await context.__aexit__(None, None, None)

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def live_snapshot(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        session_id = request.path_params["session"]
        try:
            through_value = request.query_params.get("through")
            through = int(through_value) if through_value else None
            assert runtime_reads is not None
            result = await storage.run(
                runtime_reads.live,
                session_id,
                through=through,
            )
            if result is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
        except (RuntimeSourceError, ValueError) as error:
            return _runtime_error(error)
        return JSONResponse(result.model_dump(mode="json"))

    async def session_investigation(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        session_id = request.path_params["session"]
        try:
            assert runtime_reads is not None
            result = await storage.run(
                runtime_reads.investigation,
                session_id,
            )
            if result is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
        except RuntimeSourceError as error:
            return _runtime_error(error)
        return JSONResponse(result.model_dump(mode="json"))

    async def session_wire_evidence(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        session_id = request.path_params["session"]
        try:
            sequence = int(request.path_params["sequence"])
            selected = await storage.run(runtime.session, session_id)
            if selected is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            wire_result = await storage.run(
                runtime.wire_blob,
                session_id,
                sequence,
            )
            if wire_result is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            event, body = wire_result
        except (RuntimeSourceError, ValueError) as error:
            return _runtime_error(error)
        evidence = RuntimeSessionWireEvidence(
            record_id=f"gateway:{event.seq}",
            source_ref=f"gateway.db event {event.seq}",
            timestamp=event.at,
            direction=str(event.payload.get("direction") or "unknown"),
            digest=str(event.payload.get("digest") or ""),
            bytes=len(body),
            redacted=event.payload.get("redacted") is True,
            content_base64=base64.b64encode(body).decode("ascii"),
            content_text=body.decode("utf-8", errors="replace"),
        )
        return JSONResponse(evidence.model_dump(mode="json"))

    async def live_control(request: Request) -> JSONResponse:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        try:
            payload = LiveControlRequest.model_validate(await request.json())
            receipt = await storage.run(
                runtime.control,
                request.path_params["session"],
                request_id=payload.request_id,
                action=payload.action,
                instruction=payload.instruction,
                expected_sequence=payload.expected_sequence,
            )
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_control", "detail": str(error)},
                status_code=422,
            )
        except RuntimeSourceError as error:
            return JSONResponse(
                {"error": "control_rejected", "detail": str(error)},
                status_code=409,
            )
        return JSONResponse(receipt)

    async def live_voice(request: Request) -> Response:
        if runtime is None or not runtime.available:
            return JSONResponse(
                {
                    "error": "runtime_unavailable",
                    "detail": "No launcher runtime registry is available",
                },
                status_code=503,
            )
        if not voice.available:
            return JSONResponse(
                {
                    "error": "voice_unavailable",
                    "detail": "Live voice is not configured",
                },
                status_code=503,
            )
        session_id = request.path_params["session"]
        try:
            payload = LiveVoiceRequest.model_validate(await request.json())
            assert runtime_reads is not None
            snapshot = await storage.run(
                runtime_reads.live,
                session_id,
                through=payload.expected_sequence,
            )
            if snapshot is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            if snapshot.agent_thought is None:
                return JSONResponse(
                    {
                        "error": "voice_source_unavailable",
                        "detail": (
                            "No Agent thinking excerpt exists at the requested sequence"
                        ),
                    },
                    status_code=409,
                )
            audio = await voice.synthesize(snapshot.agent_thought.text)
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_voice_request", "detail": str(error)},
                status_code=422,
            )
        except RuntimeSourceError as error:
            return _runtime_error(error)
        except VoiceUnavailableError as error:
            return JSONResponse(
                {"error": "voice_unavailable", "detail": str(error)},
                status_code=503,
            )
        except VoiceSynthesisError as error:
            return JSONResponse(
                {"error": "voice_synthesis_failed", "detail": str(error)},
                status_code=502,
            )
        return Response(
            audio,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "X-Voice-Sequence": str(payload.expected_sequence),
            },
        )

    async def runs(_request: Request) -> JSONResponse:
        available = () if benchmark is None else await storage.run(benchmark.runs)
        return JSONResponse(
            {"runs": [run.model_dump(mode="json") for run in available]}
        )

    async def recorded_session_catalog(_request: Request) -> JSONResponse:
        available = (
            ()
            if recorded_sessions is None
            else await storage.run(recorded_sessions.catalog)
        )
        return JSONResponse(
            {"sessions": [item.model_dump(mode="json") for item in available]}
        )

    async def recorded_session(request: Request) -> JSONResponse:
        if recorded_sessions is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        bundle = await storage.run(
            recorded_sessions.load,
            request.path_params["run_id"],
        )
        if bundle is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        result = await storage.run(project_recorded_session, bundle)
        return JSONResponse(result.model_dump(mode="json"))

    async def investigation(request: Request) -> JSONResponse:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = await storage.run(
            benchmark.investigation,
            request.path_params["run_id"],
        )
        if result is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(result.model_dump(mode="json"))

    async def run_knowledge_projection(request: Request) -> JSONResponse:
        if benchmark is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = await storage.run(
            benchmark.investigation,
            request.path_params["run_id"],
        )
        if result is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        projection = await storage.run(project_knowledge, result)
        return JSONResponse(projection.model_dump(mode="json"))

    async def player_knowledge(request: Request) -> JSONResponse:
        if knowledge_source is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "BOUKENSHA_DIR is not configured",
                },
                status_code=503,
            )
        after_value = request.query_params.get("after", "0")
        try:
            after = int(after_value)
        except ValueError:
            return JSONResponse(
                {"error": "invalid_cursor", "detail": "after must be an integer"},
                status_code=422,
            )
        if after < 0:
            return JSONResponse(
                {
                    "error": "invalid_cursor",
                    "detail": "after must not be negative",
                },
                status_code=422,
            )
        try:
            result = await storage.run(
                knowledge_source.read,
                request.path_params["player_id"],
                after=after,
            )
        except KnowledgeSourceError as error:
            return JSONResponse(
                {"error": "knowledge_unavailable", "detail": str(error)},
                status_code=422,
            )
        return JSONResponse(result.model_dump(mode="json"))

    async def recover_player_knowledge(request: Request) -> JSONResponse:
        if runtime is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "BOUKENSHA_DIR is not configured",
                },
                status_code=503,
            )
        try:
            payload = KnowledgeRecoveryRequest.model_validate(await request.json())
            receipt = await storage.run(
                runtime.recover_knowledge,
                payload.session_id,
                player_id=request.path_params["player_id"],
                action=payload.action,
                expected_sequence=payload.expected_sequence,
                snapshot_id=payload.snapshot_id,
                reason=payload.reason,
            )
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_recovery", "detail": str(error)},
                status_code=422,
            )
        except RuntimeSourceError as error:
            return JSONResponse(
                {"error": "recovery_rejected", "detail": str(error)},
                status_code=409,
            )
        return JSONResponse(receipt)

    async def history(request: Request) -> JSONResponse:
        if benchmark is None or recorded_sessions is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = await storage.run(
            diagnostic_history,
            benchmark,
            recorded=recorded_sessions,
            player_id=request.query_params.get("player"),
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def export_incident(request: Request) -> Response:
        if benchmark is None or recorded_sessions is None or knowledge_source is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        try:
            payload = IncidentExportRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_incident", "detail": str(error)},
                status_code=422,
            )
        bundle = await storage.run(recorded_sessions.load, payload.run_id)
        if bundle is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            result = await storage.run(
                project_recorded_session_prefix,
                bundle,
                payload.selected_record_id,
            )
        except ValueError as error:
            return JSONResponse(
                {"error": "invalid_incident", "detail": str(error)},
                status_code=422,
            )
        try:
            knowledge = await storage.run(
                knowledge_source.read,
                result.player_id,
            )
            history_result = await storage.run(
                diagnostic_history,
                benchmark,
                recorded=recorded_sessions,
                player_id=result.player_id,
            )
            capsule = await storage.run(
                build_capsule,
                payload,
                result,
                knowledge,
                history_result,
                active.revision,
            )
        except (KnowledgeSourceError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_incident", "detail": str(error)},
                status_code=422,
            )
        safe_name = "".join(
            character
            for character in result.run.journey.casefold()
            if character.isalnum() or character in {"-", "_"}
        )
        return Response(
            capsule.model_dump_json(),
            media_type="application/vnd.boukensha.incident+json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="boukensha-{safe_name}-incident.json"'
                ),
                "Cache-Control": "no-store",
            },
        )

    async def comparisons(_request: Request) -> JSONResponse:
        result = (
            None
            if active.benchmark_root is None
            else await storage.run(
                rendering_comparison,
                active.benchmark_root,
            )
        )
        return JSONResponse(
            {
                "comparisons": []
                if result is None
                else [
                    {
                        "id": result.id,
                        "title": result.title,
                        "journey": result.journey,
                    }
                ]
            }
        )

    async def experiments_catalog(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "registry": [
                    feature.model_dump(mode="json") for feature in experiment_registry()
                ],
                "scenarios": [
                    scenario.model_dump(mode="json")
                    for scenario in experiment_scenarios()
                ],
                "execution": {
                    "available": active.experiment_execution_enabled,
                    "state_store_available": experiment_executor is not None,
                    "max_spend_usd": active.experiment_max_spend_cap,
                    "paid_confirmation_required": True,
                },
            }
        )

    async def comparison(request: Request) -> JSONResponse:
        if active.benchmark_root is None:
            return JSONResponse(
                {
                    "error": "source_disabled",
                    "detail": "OBSERVATORY_BENCHMARK_ROOT is not configured",
                },
                status_code=503,
            )
        result = await storage.run(
            rendering_comparison,
            active.benchmark_root,
        )
        if result is None or result.id != request.path_params["comparison_id"]:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(result.model_dump(mode="json"))

    async def run_experiment(request: Request) -> JSONResponse:
        try:
            payload = ExperimentRunRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_experiment_run", "detail": str(error)},
                status_code=422,
            )
        if not payload.confirmed:
            return JSONResponse(
                {
                    "error": "confirmation_required",
                    "detail": (
                        "Paid execution requires explicit confirmation of the "
                        "validated definition and maximum spend."
                    ),
                },
                status_code=409,
            )
        if not active.experiment_execution_enabled:
            return JSONResponse(
                {
                    "error": "execution_disabled",
                    "detail": (
                        "Experiment execution is disabled by local policy. "
                        "Imported evidence remains available."
                    ),
                },
                status_code=503,
            )
        if experiment_executor is None:
            return JSONResponse(
                {
                    "error": "state_store_unavailable",
                    "detail": "Experiment runtime state storage is not configured.",
                },
                status_code=503,
            )
        if payload.confirmed_max_spend_usd > active.experiment_max_spend_cap:
            return JSONResponse(
                {
                    "error": "spend_cap_exceeded",
                    "detail": (
                        "The confirmed spend exceeds the configured local "
                        "experiment ceiling."
                    ),
                },
                status_code=422,
            )
        current = (
            None
            if active.benchmark_root is None
            else await storage.run(
                rendering_comparison,
                active.benchmark_root,
            )
        )
        if current is None:
            return JSONResponse(
                {"error": "registry_unavailable"},
                status_code=503,
            )
        validation = validate_definition(
            payload.definition,
            current.registry,
            execution_available=True,
            local_spend_cap=active.experiment_max_spend_cap,
        )
        if not validation.valid:
            return JSONResponse(
                {
                    "error": "validation_failed",
                    "validation": validation.model_dump(mode="json"),
                },
                status_code=422,
            )
        if (
            payload.confirmed_max_spend_usd
            != payload.definition.effective_max_spend_usd
        ):
            return JSONResponse(
                {
                    "error": "confirmation_mismatch",
                    "detail": (
                        "Confirmed spend must equal the validated effective "
                        "maximum spend."
                    ),
                },
                status_code=409,
            )
        try:
            job = await storage.run(
                experiment_executor.create,
                request_id=payload.request_id,
                definition=payload.definition,
                player_profile=payload.player_profile,
                confirmed_max_spend_usd=payload.confirmed_max_spend_usd,
            )
        except ExperimentRequestConflict as error:
            return JSONResponse(
                {"error": "request_conflict", "detail": str(error)},
                status_code=409,
            )
        await experiment_executor.start(job.id)
        return JSONResponse(job.public(), status_code=202)

    async def experiment_job(request: Request) -> JSONResponse:
        if experiment_executor is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            job = experiment_executor.require(request.path_params["job_id"])
        except KeyError:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(job.public())

    async def experiment_jobs(request: Request) -> JSONResponse:
        del request
        jobs = (
            []
            if experiment_executor is None
            else [
                job.public()
                for job in sorted(
                    experiment_executor.jobs.values(),
                    key=lambda candidate: candidate.id,
                    reverse=True,
                )
            ]
        )
        return JSONResponse({"jobs": jobs})

    async def control_experiment(request: Request) -> JSONResponse:
        if experiment_executor is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            job = experiment_executor.require(request.path_params["job_id"])
        except KeyError:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid_control"}, status_code=422)
        action = payload.get("action") if isinstance(payload, dict) else None
        if action == "stop":
            await experiment_executor.stop(job.id)
        elif action == "resume":
            await experiment_executor.start(job.id)
        else:
            return JSONResponse(
                {"error": "invalid_control", "detail": "Use stop or resume."},
                status_code=422,
            )
        return JSONResponse(job.public())

    async def validate_experiment(request: Request) -> JSONResponse:
        try:
            payload = ExperimentValidateRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_experiment", "detail": str(error)},
                status_code=422,
            )
        current = (
            None
            if active.benchmark_root is None
            else await storage.run(
                rendering_comparison,
                active.benchmark_root,
            )
        )
        if current is None:
            return JSONResponse(
                {
                    "error": "registry_unavailable",
                    "detail": "A typed experiment registry is not available.",
                },
                status_code=503,
            )
        result = validate_definition(
            payload.definition,
            current.registry,
            execution_available=active.experiment_execution_enabled,
            local_spend_cap=active.experiment_max_spend_cap,
        )
        return JSONResponse(
            {
                "validation": result.model_dump(mode="json"),
                "queue": list(sample_queue(payload.definition)),
            }
        )

    async def fork_experiment(request: Request) -> JSONResponse:
        try:
            payload = ExperimentForkRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_experiment_fork", "detail": str(error)},
                status_code=422,
            )
        current = (
            None
            if active.benchmark_root is None
            else await storage.run(
                rendering_comparison,
                active.benchmark_root,
            )
        )
        if current is None:
            return JSONResponse(
                {
                    "error": "registry_unavailable",
                    "detail": "A typed experiment registry is not available.",
                },
                status_code=503,
            )
        try:
            result = fork_one_variable(
                payload.definition,
                arm_id=payload.arm_id,
                feature_id=payload.feature_id,
                value=payload.value,
                registry=current.registry,
            )
        except ValueError as error:
            return JSONResponse(
                {"error": "invalid_experiment_fork", "detail": str(error)},
                status_code=422,
            )
        if experiment_executor is not None:
            try:
                await storage.run(
                    experiment_executor.persist_definition,
                    result,
                )
            except ValueError as error:
                return JSONResponse(
                    {
                        "error": "immutable_definition_conflict",
                        "detail": str(error),
                    },
                    status_code=409,
                )
        return JSONResponse(result.model_dump(mode="json"))

    async def world_atlas(request: Request) -> JSONResponse:
        level = request.query_params.get("level", "overview")
        if level not in {"overview", "zone"}:
            return JSONResponse(
                {"error": "invalid_level", "detail": "Use overview or zone"},
                status_code=422,
            )
        zone_value = request.query_params.get("zone")
        if level == "zone" and zone_value is None:
            return JSONResponse(
                {"error": "zone_required", "detail": "Zone detail needs zone"},
                status_code=422,
            )
        try:
            zone = int(zone_value) if zone_value is not None else None
        except ValueError:
            return JSONResponse(
                {"error": "invalid_zone", "detail": "Zone must be an integer"},
                status_code=422,
            )
        result = await storage.run(
            atlas.projection,
            level=level,
            zone=zone,
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def ask(request: Request) -> JSONResponse:
        nonlocal model_spend
        try:
            payload = AskRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_query", "detail": str(error)},
                status_code=422,
            )
        result = await storage.run(
            answer,
            payload,
            benchmark,
            recorded_sessions,
            runtime,
            experiment_executor,
            knowledge_source,
        )
        if (
            result.tier == "model_disabled"
            and payload.allow_model
            and translator is not None
        ):
            reserve = (
                1_000 * active.copilot_input_rate + 80 * active.copilot_output_rate
            ) / 1_000_000
            if model_spend + reserve <= active.copilot_spend_cap:
                try:
                    translation = await translator.translate(payload.question)
                    if translation.operation == "unsupported":
                        raise ValueError("model selected no supported operation")
                    translated_query = ObservatoryQuery(
                        operation=translation.operation,
                        scope=payload.scope,
                    )
                    translated = await storage.run(
                        answer,
                        payload.model_copy(
                            update={
                                "query": translated_query,
                                "allow_model": False,
                            }
                        ),
                        benchmark,
                        recorded_sessions,
                        runtime,
                        experiment_executor,
                        knowledge_source,
                    )
                    model_spend += translation.cost_usd
                    result = translated.model_copy(
                        update={
                            "tier": (
                                "model_translated"
                                if translated.tier != "unsupported"
                                else "unsupported"
                            ),
                            "model_cost_usd": translation.cost_usd,
                            "model_input_tokens": translation.input_tokens,
                            "model_output_tokens": translation.output_tokens,
                        }
                    )
                except (httpx.HTTPError, ValueError):
                    pass
        if (
            payload.allow_summary
            and translator is not None
            and result.tier in {"deterministic", "model_translated"}
            and result.citations
        ):
            reserve = (
                2_000 * active.copilot_input_rate + 160 * active.copilot_output_rate
            ) / 1_000_000
            if model_spend + reserve <= active.copilot_spend_cap:
                try:
                    summary = await translator.summarize(
                        question=payload.question,
                        answer=result.answer,
                        claims=tuple(
                            (claim.text, claim.citations) for claim in result.claims
                        ),
                        citations=tuple(
                            (citation.id, citation.excerpt)
                            for citation in result.citations
                        ),
                        missing=result.missing,
                    )
                    model_spend += summary.cost_usd
                    result = result.model_copy(
                        update={
                            "tier": "model_summarized",
                            "model_cost_usd": (
                                result.model_cost_usd + summary.cost_usd
                            ),
                            "model_input_tokens": (
                                result.model_input_tokens + summary.input_tokens
                            ),
                            "model_output_tokens": (
                                result.model_output_tokens + summary.output_tokens
                            ),
                            "model_summary": summary.summary,
                            "model_summary_citations": summary.citations,
                        }
                    )
                except (httpx.HTTPError, ValueError):
                    pass
        return JSONResponse(result.model_dump(mode="json"))

    async def index(_request: Request) -> Response:
        target = await storage.run(
            _existing_frontend_file,
            active.web_dist,
            Path("index.html"),
        )
        if target is None:
            return JSONResponse(
                {
                    "error": "frontend_not_built",
                    "detail": "Run npm install and npm run build in web/",
                },
                status_code=503,
            )
        return FileResponse(target)

    async def asset(request: Request) -> Response:
        target = await storage.run(
            _existing_frontend_file,
            active.web_dist,
            Path("assets") / request.path_params["path"],
        )
        if target is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return FileResponse(target)

    async def api_v1_openapi(_request: Request) -> JSONResponse:
        return JSONResponse(openapi_document())

    async def unsupported_api_version(request: Request) -> JSONResponse:
        version = request.path_params["version"]
        error = (
            ApiError(
                error="not_found",
                detail="The requested resource is not published in API version 1.",
            )
            if version == 1
            else ApiError(
                error="unsupported_api_version",
                detail=f"API version {version} is unsupported. Use /api/v1.",
            )
        )
        return JSONResponse(error.model_dump(mode="json"), status_code=404)

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        index = (
            None
            if active.runtime_root is None
            else IndexStore.for_runtime(active.runtime_root)
        )
        application.state.session_index = index
        try:
            yield
        finally:
            if index is not None:
                index.close()
            await storage.close()

    versioned_handlers = {
        "health": health,
        "capabilities": capabilities,
    }

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/api/v1/openapi.json", api_v1_openapi),
            *api_v1_routes(versioned_handlers),
            Route("/api/v{version:int}", unsupported_api_version),
            Route("/api/v{version:int}/{path:path}", unsupported_api_version),
            Route("/api/health", health),
            Route("/api/capabilities", capabilities),
            Route("/api/contracts", contracts),
            Route("/api/sessions", sessions),
            Route("/api/sessions/{session:str}/snapshot", live_snapshot),
            Route(
                "/api/sessions/{session:str}/investigation",
                session_investigation,
            ),
            Route(
                "/api/sessions/{session:str}/wire/{sequence:int}",
                session_wire_evidence,
            ),
            Route(
                "/api/sessions/{session:str}/control",
                live_control,
                methods=["POST"],
            ),
            Route(
                "/api/sessions/{session:str}/voice",
                live_voice,
                methods=["POST"],
            ),
            Route(
                "/api/sessions/{session:str}/{endpoint:str}",
                gateway_events,
            ),
            Route("/api/runs", runs),
            Route("/api/recorded-sessions", recorded_session_catalog),
            Route(
                "/api/recorded-sessions/{run_id:str}",
                recorded_session,
            ),
            Route("/api/runs/{run_id:str}/investigation", investigation),
            Route(
                "/api/runs/{run_id:str}/knowledge-projection",
                run_knowledge_projection,
            ),
            Route(
                "/api/players/{player_id:str}/knowledge",
                player_knowledge,
            ),
            Route(
                "/api/players/{player_id:str}/knowledge/recovery",
                recover_player_knowledge,
                methods=["POST"],
            ),
            Route("/api/diagnostic-history", history),
            Route("/api/incidents/export", export_incident, methods=["POST"]),
            Route("/api/comparisons", comparisons),
            Route("/api/experiments/catalog", experiments_catalog),
            Route("/api/experiments/run", run_experiment, methods=["POST"]),
            Route("/api/experiments/jobs", experiment_jobs),
            Route(
                "/api/experiments/jobs/{job_id:str}",
                experiment_job,
            ),
            Route(
                "/api/experiments/jobs/{job_id:str}/control",
                control_experiment,
                methods=["POST"],
            ),
            Route(
                "/api/experiments/validate",
                validate_experiment,
                methods=["POST"],
            ),
            Route(
                "/api/experiments/fork",
                fork_experiment,
                methods=["POST"],
            ),
            Route("/api/world/atlas", world_atlas),
            Route(
                "/api/comparisons/{comparison_id:str}",
                comparison,
            ),
            Route("/api/ask", ask, methods=["POST"]),
            Route("/assets/{path:path}", asset),
            Route("/", index),
            Route("/{path:path}", index),
        ],
    )


def _upstream_error(error: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "error": "gateway_unavailable",
            "detail": str(error),
        },
        status_code=503,
    )


def _runtime_error(error: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "error": "runtime_unavailable",
            "detail": str(error),
        },
        status_code=503,
    )


def _existing_frontend_file(root: Path, relative: Path) -> Path | None:
    canonical_root = root.resolve()
    target = (canonical_root / relative).resolve()
    if canonical_root not in target.parents or not target.is_file():
        return None
    return target


def _runtime_events(
    request: Request,
    runtime: RuntimeSource,
    storage: StorageExecutor,
    session_id: str,
    endpoint: str,
) -> StreamingResponse:
    after_value = request.query_params.get("after")
    header_value = request.headers.get("last-event-id")
    cursor = int(after_value or header_value or "0")
    limit_value = request.query_params.get("limit")
    limit = int(limit_value) if limit_value else None
    tail = request.query_params.get("tail", "1") != "0"

    async def body() -> AsyncIterator[str]:
        nonlocal cursor
        delivered = 0
        while True:
            try:
                events = await storage.run(
                    runtime.events,
                    session_id,
                    after=cursor,
                    limit=(None if limit is None else max(0, limit - delivered)),
                )
            except RuntimeSourceError:
                return
            for event in events:
                cursor = event.seq
                delivered += 1
                yield serialize_event(event)
                if limit is not None and delivered >= limit:
                    return
            if endpoint == "replay" or not tail:
                return
            try:
                selected = await storage.run(runtime.session, session_id)
            except RuntimeSourceError:
                return
            if selected is None or (
                not selected.live and cursor >= selected.latest_seq
            ):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    arguments = parser.parse_args()
    uvicorn.run(
        create_app(),
        host=arguments.host,
        port=arguments.port,
    )


if __name__ == "__main__":
    main()
