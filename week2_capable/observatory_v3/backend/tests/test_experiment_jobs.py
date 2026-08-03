from __future__ import annotations

import asyncio
import shutil
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from observatory_v3_backend.app import create_app
from observatory_v3_backend.contracts import (
    AskRequest,
    ExperimentDefinition,
    ObservatoryQuery,
    QueryScope,
)
from observatory_v3_backend.execution import (
    ExperimentDefinitionConflict,
    ExperimentExecutor,
    ExperimentIdentityConflict,
    ExperimentJob,
    ExperimentSample,
    ExperimentStateConflict,
    ExperimentStore,
    SampleResult,
    SubprocessExperimentRunner,
)
from observatory_v3_backend.experiment_catalog import experiment_registry
from observatory_v3_backend.experiment_jobs.models import TERMINAL_SAMPLE_STATES
from observatory_v3_backend.queries import experiments as experiment_queries
from observatory_v3_backend.settings import Settings
from observatory_v3_backend.sources.comparison import rendering_definition
from observatory_v3_backend.storage_executor import StorageExecutor

from .fixtures import build_retained_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class SuccessfulRunner:
    def __init__(self) -> None:
        self.launches: list[str] = []

    def dry_run(
        self,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> tuple[tuple[str, ...], Mapping[str, str]]:
        return (
            (
                "runner",
                "--sample",
                sample.id,
                "--profile",
                str(sample.effective_config["tools.profile"]),
            ),
            {
                "BOUKENSHA_EXPERIMENT_ID": job.id,
                "BOUKENSHA_RUN_ID": sample.id,
            },
        )

    async def run(
        self,
        _job: ExperimentJob,
        sample: ExperimentSample,
    ) -> SampleResult:
        self.launches.append(sample.id)
        return SampleResult(
            state="success",
            detail="verified predicate passed",
            cost_usd=0.1,
            turns=3,
            calls=4,
        )

    async def stop(self, _job_id: str) -> None:
        return None


def _definition() -> ExperimentDefinition:
    original = rendering_definition()
    return original.model_copy(
        update={
            "repetitions_per_arm": 1,
            "effective_max_spend_usd": 1.8,
            "stop": original.stop.model_copy(update={"success_target": 3}),
        }
    )


def _executor(
    tmp_path: Path,
    runner: SuccessfulRunner,
) -> ExperimentExecutor:
    return ExperimentExecutor(
        tmp_path / "experiments",
        benchmark_root=tmp_path / "benchmarks",
        storage=StorageExecutor(capacity=2),
        repository_root=tmp_path,
        runner=runner,
        session_resolver=lambda experiment_id, run_id: (
            f"session:{experiment_id}:{run_id}"
        ),
    )


def test_model_free_dry_run_has_stable_identity_and_safe_direct_argv(
    tmp_path: Path,
) -> None:
    runner = SuccessfulRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="dry-run",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    first = next(iter(job.samples.values()))

    command, environment = executor.dry_run(job.id, first.id)

    assert runner.launches == []
    assert command == (
        "runner",
        "--sample",
        first.id,
        "--profile",
        first.effective_config["tools.profile"],
    )
    assert environment == {
        "BOUKENSHA_EXPERIMENT_ID": job.id,
        "BOUKENSHA_RUN_ID": first.id,
    }
    assert not any("|" in item or ";" in item for item in command)


def test_installed_runner_rejects_unregistered_effective_config(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    job, _created = store.create(
        request_id="typed-config",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    sample = next(iter(job.samples.values()))
    sample.effective_config["unknown.option"] = True
    runner = SubprocessExperimentRunner(
        benchmark_root=tmp_path / "benchmarks",
        repository_root=REPOSITORY_ROOT,
    )

    with pytest.raises(ValueError, match="unknown fields"):
        runner.dry_run(job, sample)


def test_restart_reconciles_in_flight_sample_without_relaunch(
    tmp_path: Path,
) -> None:
    runner = SuccessfulRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="restart",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    sample = next(iter(job.samples.values()))
    executor.store.set_sample_state(
        job.id,
        sample.id,
        "launching",
        detail="process claimed",
        run_id=sample.id,
    )
    executor.store.set_sample_state(
        job.id,
        sample.id,
        "running",
        detail="process started",
        run_id=sample.id,
    )
    executor.store.set_job_state(job.id, "running", current_sample=sample.id)
    executor.store.close()

    reopened = _executor(tmp_path, runner)
    asyncio.run(reopened.reconcile())
    recovered = reopened.require(job.id)

    assert runner.launches == []
    assert recovered.state == "stopped"
    assert recovered.current_sample is None
    assert recovered.samples[sample.id].state == "interrupted"
    assert recovered.samples[sample.id].run_id == sample.id
    assert "not relaunched" in recovered.samples[sample.id].detail


async def test_execution_links_every_sample_to_one_canonical_session(
    tmp_path: Path,
) -> None:
    runner = SuccessfulRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="canonical",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )

    await executor.start(job.id)
    await executor.tasks[job.id]
    retained = executor.require(job.id)

    assert retained.state == "completed"
    assert runner.launches == list(retained.samples)
    assert retained.spent_usd == 0.3
    assert retained.aggregates() == {
        "planned": 3,
        "queued": 0,
        "running": 0,
        "success": 3,
        "failed": 0,
        "cancelled": 0,
        "excluded": 0,
        "spent_usd": 0.3,
    }
    assert all(
        sample.session_id == f"session:{job.id}:{sample.id}"
        for sample in retained.samples.values()
    )


async def test_stop_and_resume_preserve_queue_and_spend_identity(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingRunner(SuccessfulRunner):
        async def run(
            self,
            _job: ExperimentJob,
            sample: ExperimentSample,
        ) -> SampleResult:
            self.launches.append(sample.id)
            started.set()
            await release.wait()
            return SampleResult(
                state="cancelled",
                detail="operator stopped sample",
            )

        async def stop(self, _job_id: str) -> None:
            release.set()

    runner = BlockingRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="stop-resume",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    queue = tuple(job.samples)

    await executor.start(job.id)
    await started.wait()
    await executor.stop(job.id)
    await executor.tasks[job.id]
    stopped = executor.require(job.id)
    spent_at_stop = stopped.spent_usd

    runner.run = SuccessfulRunner().run  # type: ignore[method-assign]
    await executor.start(job.id)
    await executor.tasks[job.id]
    resumed = executor.require(job.id)

    assert tuple(resumed.samples) == queue
    assert resumed.spent_usd >= spent_at_stop
    assert runner.launches.count(queue[0]) == 1
    assert resumed.samples[queue[0]].state == "cancelled"


async def test_reported_overspend_is_retained_and_stops_the_job(
    tmp_path: Path,
) -> None:
    class OverspendRunner(SuccessfulRunner):
        async def run(
            self,
            _job: ExperimentJob,
            sample: ExperimentSample,
        ) -> SampleResult:
            self.launches.append(sample.id)
            return SampleResult(
                state="success",
                detail="runner claimed success",
                cost_usd=0.7,
            )

    runner = OverspendRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="overspend",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )

    await executor.start(job.id)
    await executor.tasks[job.id]
    retained = executor.require(job.id)
    sample = next(iter(retained.samples.values()))

    assert retained.state == "failed"
    assert retained.spent_usd == 0.7
    assert sample.state == "setup_failure"
    assert sample.detail == "Runner reported spend beyond the confirmed budget"
    assert runner.launches == [sample.id]
    with pytest.raises(ExperimentStateConflict):
        await executor.start(job.id)


async def test_concurrency_never_exceeds_the_typed_definition_limit(
    tmp_path: Path,
) -> None:
    class ConcurrentRunner(SuccessfulRunner):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.high_water = 0

        async def run(
            self,
            _job: ExperimentJob,
            sample: ExperimentSample,
        ) -> SampleResult:
            self.launches.append(sample.id)
            self.active += 1
            self.high_water = max(self.high_water, self.active)
            try:
                await asyncio.sleep(0.01)
                return SampleResult(
                    state="success",
                    detail="verified",
                    cost_usd=0.1,
                )
            finally:
                self.active -= 1

    runner = ConcurrentRunner()
    executor = _executor(tmp_path, runner)
    definition = _definition().model_copy(
        update={
            "repetitions_per_arm": 2,
            "concurrency": 3,
            "effective_max_spend_usd": 3.6,
            "stop": _definition().stop.model_copy(update={"success_target": 6}),
        }
    )
    job = executor.create(
        request_id="concurrency",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=3.6,
    )

    await executor.start(job.id)
    await executor.tasks[job.id]

    assert runner.high_water == 3
    assert executor.require(job.id).state == "completed"


async def test_early_success_excludes_unneeded_queue_after_active_exit(
    tmp_path: Path,
) -> None:
    runner = SuccessfulRunner()
    executor = _executor(tmp_path, runner)
    definition = _definition().model_copy(
        update={
            "repetitions_per_arm": 2,
            "concurrency": 2,
            "effective_max_spend_usd": 3.6,
            "stop": _definition().stop.model_copy(update={"success_target": 1}),
        }
    )
    job = executor.create(
        request_id="early-target",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=3.6,
    )

    await executor.start(job.id)
    await executor.tasks[job.id]
    retained = executor.require(job.id)

    assert retained.state == "completed"
    assert all(
        sample.state not in {"queued", "launching", "running"}
        for sample in retained.samples.values()
    )
    assert retained.aggregates()["excluded"] >= 4


async def test_runner_exception_retains_samples_before_terminal_job(
    tmp_path: Path,
) -> None:
    class FailingRunner(SuccessfulRunner):
        async def run(
            self,
            _job: ExperimentJob,
            sample: ExperimentSample,
        ) -> SampleResult:
            self.launches.append(sample.id)
            raise RuntimeError("runner broke")

    runner = FailingRunner()
    executor = _executor(tmp_path, runner)
    job = executor.create(
        request_id="runner-error",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )

    await executor.start(job.id)
    await executor.tasks[job.id]
    retained = executor.require(job.id)

    assert retained.state == "failed"
    assert runner.launches == [next(iter(job.samples))]
    assert [sample.state for sample in retained.samples.values()] == [
        "setup_failure",
        "excluded",
        "excluded",
    ]
    assert retained.samples[runner.launches[0]].detail == "Runner failed: runner broke"
    assert all(
        sample.detail == "Runner setup failure stopped the execution queue"
        for sample in tuple(retained.samples.values())[1:]
    )
    assert retained.terminal_reason == (
        "Runner setup failure stopped the execution queue"
    )


def test_overspend_reconciliation_finalizes_every_queued_sample(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    job, _created = store.create(
        request_id="crash-window-overspend",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    first = next(iter(job.samples.values()))
    store.claim_sample(job.id, first.id)
    store.set_sample_state(
        job.id,
        first.id,
        "running",
        detail="process started",
        run_id=first.id,
    )
    store.record_result(
        job.id,
        first.id,
        SampleResult(
            state="success",
            detail="result persisted before supervisor accounting",
            cost_usd=0.7,
        ),
    )

    (retained,) = store.reconcile_spend_and_budgets()

    assert retained.state == "failed"
    assert retained.launch_blocked is True
    assert retained.terminal_reason == ("Retained spend exceeds an execution ceiling")
    assert retained.samples[first.id].state == "success"
    queued = tuple(retained.samples.values())[1:]
    assert all(sample.state == "excluded" for sample in queued)
    assert all(
        sample.detail == "Retained spend exceeds an execution ceiling"
        for sample in queued
    )
    assert all(sample.finished_at is not None for sample in queued)
    assert all(
        sample.state in TERMINAL_SAMPLE_STATES for sample in retained.samples.values()
    )


def test_experiment_ask_fetches_only_one_bounded_job_and_sample_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _executor(tmp_path, SuccessfulRunner())
    selected = None
    for index in range(20):
        selected = executor.create(
            request_id=f"ask-job-{index:02d}",
            definition=_definition(),
            player_profile="poucet",
            confirmed_max_spend_usd=1.8,
        )
    assert selected is not None
    scope = QueryScope(space="experiments", subject_id=selected.id)
    query = ObservatoryQuery(
        operation="list_experiment_samples",
        scope=scope,
        limit=1,
    )
    request = AskRequest(
        question="Show one selected sample",
        scope=scope,
        query=query,
    )
    original_get = executor.store.get
    get_calls = 0

    def counted_get(*args: object, **kwargs: object) -> ExperimentJob:
        nonlocal get_calls
        get_calls += 1
        return original_get(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(executor.store, "get", counted_get)

    response = experiment_queries.samples(request, None, executor, query)

    assert len(response.citations) == 1
    assert response.citations[0].id.startswith(f"experiment:{selected.id}:")
    assert get_calls == 1


async def test_stop_is_idempotent_before_any_sample_launch(
    tmp_path: Path,
) -> None:
    executor = _executor(tmp_path, SuccessfulRunner())
    job = executor.create(
        request_id="queued-stop",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )

    first = await executor.stop(job.id)
    second = await executor.stop(job.id)

    assert first.state == "stopped"
    assert second.state == "stopped"
    assert first.samples.keys() == second.samples.keys()


def test_sample_metrics_must_be_finite_and_nonnegative() -> None:
    with pytest.raises(ValueError):
        SampleResult(state="success", detail="invalid", cost_usd=float("nan"))
    with pytest.raises(ValueError):
        SampleResult(state="success", detail="invalid", cost_usd=float("inf"))
    with pytest.raises(ValueError):
        SampleResult(state="success", detail="invalid", turns=-1)


def test_session_links_are_idempotent_and_scoped_by_experiment(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    first, _created = store.create(
        request_id="identity-first",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    second, _created = store.create(
        request_id="identity-second",
        definition=_definition(),
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    first_sample = next(iter(first.samples.values()))
    second_sample = next(iter(second.samples.values()))

    store.link_session(
        first.id,
        first_sample.id,
        run_id=first_sample.id,
        session_id="session-first",
    )
    repeated = store.link_session(
        first.id,
        first_sample.id,
        run_id=first_sample.id,
        session_id="session-first",
    )
    cross_job = store.link_session(
        second.id,
        second_sample.id,
        run_id=second_sample.id,
        session_id="session-second",
    )

    assert repeated.samples[first_sample.id].session_id == "session-first"
    assert cross_job.samples[second_sample.id].session_id == "session-second"
    with pytest.raises(ExperimentIdentityConflict):
        store.link_session(
            first.id,
            first_sample.id,
            run_id=first_sample.id,
            session_id="different-session",
        )


def test_immutable_definition_and_derived_aggregates_survive_reopen(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    definition = _definition()
    job, created = store.create(
        request_id="aggregate",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    samples = list(job.samples)
    for sample_id in samples:
        store.set_sample_state(
            job.id,
            sample_id,
            "launching",
            detail="sample claimed",
            run_id=sample_id,
        )
        store.set_sample_state(
            job.id,
            sample_id,
            "running",
            detail="process started",
        )
    store.record_result(
        job.id,
        samples[0],
        SampleResult(state="success", detail="ok", cost_usd=0.2),
    )
    store.record_result(
        job.id,
        samples[1],
        SampleResult(state="agent_failure", detail="predicate failed", cost_usd=0.3),
    )
    store.record_result(
        job.id,
        samples[2],
        SampleResult(state="setup_failure", detail="setup failed"),
    )
    store.close()

    reopened = ExperimentStore(tmp_path / "experiments")
    retained = reopened.get(job.id)

    assert created is True
    assert retained.definition == definition
    assert retained.spent_usd == 0.5
    assert retained.aggregates()["failed"] == 2
    assert retained.aggregates()["spent_usd"] == 0.5
    changed = definition.model_copy(update={"title": "Conflicting content"})
    with pytest.raises(ExperimentDefinitionConflict):
        reopened.create(
            request_id="conflicting-definition",
            definition=changed,
            player_profile="poucet",
            confirmed_max_spend_usd=1.8,
        )


async def test_durable_experiment_resources_open_canonical_sessions(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    state_root = tmp_path / "experiments"
    store = ExperimentStore(state_root)
    job, _created = store.create(
        request_id="resource-job",
        definition=_definition(),
        player_profile="alpha",
        confirmed_max_spend_usd=1.8,
    )
    samples = list(job.samples.values())
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        for session_index, sample in enumerate(samples):
            database.execute(
                """
                UPDATE sessions SET experiment_id = ?, run_id = ?
                WHERE session_id = ?
                """,
                (job.id, sample.id, f"session-{session_index:03d}"),
            )
            store.set_sample_state(
                job.id,
                sample.id,
                "launching",
                detail="sample claimed",
                run_id=sample.id,
            )
            store.set_sample_state(
                job.id,
                sample.id,
                "running",
                detail="process started",
            )
            store.set_sample_state(
                job.id,
                sample.id,
                "success",
                detail="retained",
                run_id=sample.id,
            )
            store.link_session(
                job.id,
                sample.id,
                run_id=sample.id,
                session_id=f"session-{session_index:03d}",
            )
    store.set_job_state(job.id, "running")
    store.complete_success_target(job.id)
    store.close()
    app = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            benchmark_root=tmp_path / "benchmarks",
            experiment_state_root=state_root,
            web_dist=tmp_path / "web",
        )
    )
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://observatory",
        ) as client:
            catalog = await client.get("/api/v1/experiments")
            detail = await client.get(f"/api/v1/experiments/{job.id}")
            jobs = await client.get("/api/v1/experiments/jobs")
            sample_page = await client.get(
                f"/api/v1/experiments/jobs/{job.id}",
                params={"limit": 1},
            )
            next_sample_page = await client.get(
                f"/api/v1/experiments/jobs/{job.id}",
                params={
                    "limit": 1,
                    "cursor": sample_page.json()["continuation_cursor"],
                },
            )
            invalid_control = await client.post(
                f"/api/v1/experiments/jobs/{job.id}/control",
                json={"action": "stop", "unexpected": True},
            )
    finally:
        await lifespan.__aexit__(None, None, None)

    assert catalog.status_code == 200
    assert catalog.json()["definitions"]
    assert catalog.json()["jobs"][0]["id"] == job.id
    assert detail.status_code == 200
    assert detail.json()["completeness"] == "complete"
    assert detail.json()["aggregates"]["planned"] == 3
    assert detail.json()["session_links"] == [
        "session-000",
        "session-001",
        "session-002",
    ]
    assert jobs.status_code == 200
    assert jobs.json()["jobs"][0]["id"] == job.id
    assert jobs.json()["jobs"][0]["samples"] == []
    assert jobs.json()["jobs"][0]["launch_blocked"] is False
    assert jobs.json()["jobs"][0]["terminal_reason"]
    assert sample_page.status_code == 200
    assert len(sample_page.json()["samples"]) == 1
    assert sample_page.json()["continuation_cursor"]
    assert next_sample_page.status_code == 200
    assert len(next_sample_page.json()["samples"]) == 1
    assert (
        next_sample_page.json()["samples"][0]["queue_position"]
        > sample_page.json()["samples"][0]["queue_position"]
    )
    assert invalid_control.status_code == 422
    assert invalid_control.json()["error"] == "invalid_control"


async def test_sql_pages_cover_large_jobs_definitions_and_sample_queues(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    state_root = tmp_path / "experiments"
    store = ExperimentStore(state_root)
    for index in range(51):
        definition = _definition().model_copy(
            update={
                "id": f"definition-{index:03d}",
                "title": f"Definition {index}",
            }
        )
        store.create(
            request_id=f"job-{index:03d}",
            definition=definition,
            player_profile="alpha",
            confirmed_max_spend_usd=1.8,
        )
    large_definition = _definition().model_copy(
        update={
            "id": "definition-paged",
            "repetitions_per_arm": 40,
            "effective_max_spend_usd": 72.0,
            "stop": _definition().stop.model_copy(
                update={
                    "success_target": 120,
                    "max_total_cost_usd": 72.0,
                }
            ),
        }
    )
    large, _created = store.create(
        request_id="paged-job",
        definition=large_definition,
        player_profile="alpha",
        confirmed_max_spend_usd=72.0,
    )
    store.close()
    app = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            benchmark_root=tmp_path / "benchmarks",
            experiment_state_root=state_root,
            web_dist=tmp_path / "web",
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://observatory",
        ) as client:
            first_jobs = await client.get(
                "/api/v1/experiments/jobs",
                params={"limit": 50},
            )
            second_jobs = await client.get(
                "/api/v1/experiments/jobs",
                params={
                    "limit": 50,
                    "cursor": first_jobs.json()["continuation_cursor"],
                },
            )
            first_catalog = await client.get(
                "/api/v1/experiments",
                params={"limit": 50},
            )
            second_catalog = await client.get(
                "/api/v1/experiments",
                params={
                    "limit": 50,
                    "cursor": first_catalog.json()["continuation_cursor"],
                },
            )
            first_samples = await client.get(
                f"/api/v1/experiments/jobs/{large.id}",
                params={"limit": 100},
            )
            second_samples = await client.get(
                f"/api/v1/experiments/jobs/{large.id}",
                params={
                    "limit": 100,
                    "cursor": first_samples.json()["continuation_cursor"],
                },
            )
            first_detail = await client.get(
                f"/api/v1/experiments/{large.id}",
                params={"limit": 100},
            )
            second_detail = await client.get(
                f"/api/v1/experiments/{large.id}",
                params={
                    "limit": 100,
                    "cursor": first_detail.json()["continuation_cursor"],
                },
            )

    assert first_jobs.status_code == 200
    assert len(first_jobs.json()["jobs"]) == 50
    assert len(second_jobs.json()["jobs"]) == 2
    assert len(first_catalog.json()["jobs"]) == 50
    assert len(second_catalog.json()["jobs"]) == 2
    assert len(first_catalog.json()["definitions"]) == 50
    assert len(second_catalog.json()["definitions"]) == 2
    assert len(first_samples.json()["samples"]) == 100
    assert len(second_samples.json()["samples"]) == 20
    assert len(first_detail.json()["queue"]) == 100
    assert len(second_detail.json()["queue"]) == 20
    first_positions = {
        sample["queue_position"] for sample in first_samples.json()["samples"]
    }
    second_positions = {
        sample["queue_position"] for sample in second_samples.json()["samples"]
    }
    assert first_positions.isdisjoint(second_positions)


async def test_startup_reconciliation_tolerates_missing_runtime_registry(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "experiments"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    store = ExperimentStore(state_root)
    job, _created = store.create(
        request_id="missing-registry",
        definition=_definition(),
        player_profile="alpha",
        confirmed_max_spend_usd=1.8,
    )
    sample = next(iter(job.samples.values()))
    store.set_sample_state(
        job.id,
        sample.id,
        "launching",
        detail="sample claimed",
        run_id=sample.id,
    )
    store.set_sample_state(
        job.id,
        sample.id,
        "running",
        detail="process started",
    )
    store.record_result(
        job.id,
        sample.id,
        SampleResult(state="success", detail="retained", cost_usd=0.1),
    )
    store.close()
    app = create_app(
        Settings(
            runtime_root=runtime_root,
            benchmark_root=tmp_path / "benchmarks",
            experiment_state_root=state_root,
            web_dist=tmp_path / "web",
        )
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://observatory",
        ) as client:
            response = await client.get(
                f"/api/v1/experiments/jobs/{job.id}",
            )
    assert response.status_code == 200
    assert response.json()["samples"][0]["session_id"] is None


async def test_cold_experiment_launch_attaches_canonical_session_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    staging = tmp_path / "launcher"
    staging.mkdir()
    fixture = build_retained_fixture(staging, session_count=1)
    definition = _definition().model_copy(
        update={
            "stop": _definition().stop.model_copy(update={"success_target": 1}),
        }
    )

    async def create_first_registry(
        _runner: SubprocessExperimentRunner,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> SampleResult:
        shutil.copytree(fixture.config_dir, runtime_root, dirs_exist_ok=True)
        session_dir = (
            runtime_root
            / "profiles"
            / "alpha"
            / "sessions"
            / fixture.selected_session_id
        )
        with sqlite3.connect(runtime_root / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET experiment_id = ?, run_id = ?, session_dir = ?,
                    manifest_path = ?
                WHERE session_id = ?
                """,
                (
                    job.id,
                    sample.id,
                    str(session_dir),
                    str(session_dir / "session.json"),
                    fixture.selected_session_id,
                ),
            )
        return SampleResult(
            state="success",
            detail="model-free launcher fixture completed",
            cost_usd=0.1,
        )

    monkeypatch.setattr(SubprocessExperimentRunner, "run", create_first_registry)
    monkeypatch.setattr(
        "observatory_v3_backend.app.rendering_comparison",
        lambda _root: SimpleNamespace(registry=experiment_registry()),
    )
    application = create_app(
        Settings(
            runtime_root=runtime_root,
            benchmark_root=tmp_path / "benchmarks",
            experiment_state_root=tmp_path / "experiments",
            experiment_execution_enabled=True,
            experiment_max_spend_cap=10,
            web_dist=tmp_path / "web",
        )
    )

    async with application.router.lifespan_context(application):
        assert application.state.read_resources is None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            launched = await client.post(
                "/api/v1/experiments/run",
                json={
                    "request_id": "cold-bootstrap",
                    "definition": definition.model_dump(mode="json"),
                    "player_profile": "alpha",
                    "confirmed": True,
                    "confirmed_max_spend_usd": 1.8,
                },
            )
            assert launched.status_code == 202
            job_id = launched.json()["id"]
            for _ in range(100):
                retained = await client.get(f"/api/v1/experiments/jobs/{job_id}")
                if retained.json()["state"] == "completed":
                    break
                await asyncio.sleep(0.01)
            sessions = await client.get("/api/v1/sessions")

        assert retained.json()["state"] == "completed"
        assert retained.json()["samples"][0]["session_id"] == (
            fixture.selected_session_id
        )
        assert sessions.status_code == 200
        assert [item["id"] for item in sessions.json()["sessions"]] == [
            fixture.selected_session_id
        ]
        assert application.state.read_resources is not None
        assert application.state.session_materializer is not None
        assert application.state.session_notifications is not None


async def test_api_reports_immutable_definition_conflict_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "experiments"
    benchmark_root = tmp_path / "benchmarks"
    benchmark_root.mkdir()
    store = ExperimentStore(state_root)
    original = _definition()
    store.create(
        request_id="existing-definition",
        definition=original,
        player_profile="alpha",
        confirmed_max_spend_usd=1.8,
    )
    store.close()
    changed = original.model_copy(update={"title": "Different immutable content"})
    monkeypatch.setattr(
        "observatory_v3_backend.app.rendering_comparison",
        lambda _root: SimpleNamespace(registry=experiment_registry()),
    )
    app = create_app(
        Settings(
            benchmark_root=benchmark_root,
            experiment_state_root=state_root,
            experiment_execution_enabled=True,
            experiment_max_spend_cap=10,
            web_dist=tmp_path / "web",
        )
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://observatory",
        ) as client:
            response = await client.post(
                "/api/v1/experiments/run",
                json={
                    "request_id": "conflicting-definition",
                    "definition": changed.model_dump(mode="json"),
                    "player_profile": "alpha",
                    "confirmed": True,
                    "confirmed_max_spend_usd": 1.8,
                },
            )

    assert response.status_code == 409
    assert response.json()["error"] == "immutable_definition_conflict"
