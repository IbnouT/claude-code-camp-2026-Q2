"""Durable experiment supervisor and restart reconciliation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from ..contracts import ExperimentDefinition, ObservatoryQuery
from ..storage_executor import StorageExecutor
from .models import (
    TERMINAL_SAMPLE_STATES,
    ExperimentJob,
    ExperimentJobState,
    ExperimentSample,
    ExperimentSampleState,
    SampleResult,
)
from .runner import ExperimentRunner, SubprocessExperimentRunner
from .store import (
    TERMINAL_JOB_STATES,
    ExperimentIdentityConflict,
    ExperimentStateConflict,
    ExperimentStore,
)

ExperimentObserver = Callable[[ExperimentJob], Awaitable[None] | None]
SessionResolver = Callable[[str, str], Awaitable[str | None] | str | None]


class ExperimentExecutor:
    """Persist before effects and supervise one bounded durable queue."""

    def __init__(
        self,
        state_root: Path,
        *,
        benchmark_root: Path,
        storage: StorageExecutor,
        repository_root: Path | None = None,
        runner: ExperimentRunner | None = None,
        session_resolver: SessionResolver | None = None,
        observer: ExperimentObserver | None = None,
    ) -> None:
        self.store = ExperimentStore(state_root)
        self.storage = storage
        self.runner = runner or SubprocessExperimentRunner(
            benchmark_root=benchmark_root,
            repository_root=repository_root,
        )
        self.session_resolver = session_resolver
        self.observer = observer
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.sample_tasks: dict[str, dict[str, asyncio.Task[None]]] = {}
        self._closing = False

    def set_observer(self, observer: ExperimentObserver | None) -> None:
        self.observer = observer

    def set_session_resolver(self, resolver: SessionResolver | None) -> None:
        self.session_resolver = resolver

    def create(
        self,
        *,
        request_id: str,
        definition: ExperimentDefinition,
        player_profile: str,
        confirmed_max_spend_usd: float,
    ) -> ExperimentJob:
        job, _created = self.store.create(
            request_id=request_id,
            definition=definition,
            player_profile=player_profile,
            confirmed_max_spend_usd=confirmed_max_spend_usd,
        )
        return job

    def persist_definition(self, definition: ExperimentDefinition) -> Path:
        """Retain a definition through the same immutable SQLite boundary."""
        self.store.persist_definition(definition)
        return self.store.path

    async def reconcile(self) -> tuple[ExperimentJob, ...]:
        """Reconcile process uncertainty, spend, and canonical sessions."""
        changed: dict[str, ExperimentJob] = {}
        interrupted = await self.storage.run(self.store.reconcile_interrupted)
        changed.update((job.id, job) for job in interrupted)
        budgeted = await self.storage.run(self.store.reconcile_spend_and_budgets)
        changed.update((job.id, job) for job in budgeted)
        if self.session_resolver is not None:
            identities = await self.storage.run(self.store.samples_with_run_identity)
            for job_id, sample_id, run_id, retained_session_id in identities:
                resolved = self.session_resolver(job_id, run_id)
                session_id = (
                    await resolved if inspect.isawaitable(resolved) else resolved
                )
                if session_id is None:
                    continue
                if (
                    retained_session_id is not None
                    and retained_session_id != session_id
                ):
                    raise ExperimentIdentityConflict(
                        "canonical session reconciliation conflicts with "
                        "retained experiment identity"
                    )
                linked = await self.storage.run(
                    self.store.link_session,
                    job_id,
                    sample_id,
                    run_id=run_id,
                    session_id=session_id,
                )
                changed[job_id] = linked
        for job in changed.values():
            await self._best_effort_notify(job)
        return tuple(changed.values())

    async def start(self, job_id: str) -> ExperimentJob:
        if self._closing:
            raise ExperimentStateConflict("experiment executor is closing")
        active = self.tasks.get(job_id)
        if active is not None and not active.done():
            return self.require(job_id)
        job = self.require(job_id)
        if job.state in TERMINAL_JOB_STATES or job.state == "stopping":
            raise ExperimentStateConflict(
                f"experiment jobs in {job.state} state cannot resume"
            )
        if job.launch_blocked:
            raise ExperimentStateConflict(
                "budget-blocked experiment jobs cannot resume"
            )
        job = await self.storage.run(
            self.store.set_job_state,
            job_id,
            "running",
            stop_requested=False,
            terminal_reason="Execution is active",
        )
        await self._best_effort_notify(job)
        self.tasks[job_id] = asyncio.create_task(
            self._run(job_id),
            name=f"experiment:{job_id}",
        )
        return self.require(job_id)

    async def stop(self, job_id: str) -> ExperimentJob:
        job = self.require(job_id)
        if job.state in TERMINAL_JOB_STATES or job.state == "stopped":
            return job
        if job.state == "queued":
            job = await self.storage.run(
                self.store.set_job_state,
                job_id,
                "stopped",
                stop_requested=False,
                terminal_reason="Operator stopped the queued experiment",
            )
            await self._best_effort_notify(job)
            return self.require(job_id)
        job = await self.storage.run(
            self.store.set_job_state,
            job_id,
            "stopping",
            stop_requested=True,
            current_sample=job.current_sample,
            terminal_reason="Operator stop requested",
        )
        await self._best_effort_notify(job)
        await self.runner.stop(job_id)
        active = self.tasks.get(job_id)
        if active is not None and not active.done():
            try:
                await asyncio.wait_for(asyncio.shield(active), timeout=10)
            except TimeoutError:
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
        else:
            await self._cancel_retained_active(job_id, "Operator stopped execution")
        current = self.require(job_id)
        if current.state not in TERMINAL_JOB_STATES and current.state != "stopped":
            await self._transition_job(
                job_id,
                "stopped",
                reason="Operator stopped execution",
                stop_requested=False,
            )
        return self.require(job_id)

    def require(self, job_id: str) -> ExperimentJob:
        try:
            return self.store.get(job_id)
        except KeyError as error:
            raise KeyError(f"unknown experiment job {job_id!r}") from error

    def query_samples(
        self,
        job_id: str,
        query: ObservatoryQuery,
    ) -> tuple[ExperimentJob, tuple[ExperimentSample, ...]]:
        """Load one job header and only its bounded matching samples."""
        try:
            job = self.store.get(job_id, sample_limit=0)
        except KeyError as error:
            raise KeyError(f"unknown experiment job {job_id!r}") from error
        return job, self.store.query_samples(job_id, query)

    def dry_run(
        self,
        job_id: str,
        sample_id: str | None = None,
    ) -> tuple[tuple[str, ...], Mapping[str, str]]:
        job = self.require(job_id)
        sample = (
            next(iter(job.samples.values()))
            if sample_id is None
            else job.samples[sample_id]
        )
        return self.runner.dry_run(job, sample)

    def sample_command(
        self,
        *,
        job: ExperimentJob,
        output: Path,
        result_mode: str,
        effective_config: dict[str, bool | int | float | str],
    ) -> tuple[str, ...]:
        """Compatibility helper over the typed runner dry-run."""
        sample = next(iter(job.samples.values()))
        candidate = ExperimentSample(
            id=sample.id,
            arm_id=sample.arm_id,
            ordinal=sample.ordinal,
            queue_position=sample.queue_position,
            state=sample.state,
            effective_config=effective_config,
        )
        command, _environment = self.runner.dry_run(job, candidate)
        values = list(command)
        values[values.index("--output-dir") + 1] = str(output)
        values[values.index("--result-mode") + 1] = result_mode
        return tuple(values)

    def _persist(self, job: ExperimentJob) -> None:
        self.store.replace_for_compatibility(job)

    async def close(self) -> None:
        self._closing = True
        active_job_ids = [
            job_id for job_id, task in self.tasks.items() if not task.done()
        ]
        for job_id in active_job_ids:
            job = self.require(job_id)
            if job.state == "running":
                await self.storage.run(
                    self.store.set_job_state,
                    job_id,
                    "stopping",
                    stop_requested=True,
                    current_sample=job.current_sample,
                    terminal_reason="Executor shutdown requested",
                )
        await asyncio.gather(
            *(self.runner.stop(job_id) for job_id in active_job_ids),
            return_exceptions=True,
        )
        active_tasks = [task for task in self.tasks.values() if not task.done()]
        if active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*active_tasks),
                    timeout=10,
                )
            except TimeoutError:
                for task in active_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*active_tasks, return_exceptions=True)
        await asyncio.to_thread(self.store.close)

    async def _run(self, job_id: str) -> None:
        owned = self.sample_tasks.setdefault(job_id, {})
        try:
            while True:
                job = self.require(job_id)
                done_ids = [
                    sample_id for sample_id, task in owned.items() if task.done()
                ]
                for sample_id in done_ids:
                    task = owned.pop(sample_id)
                    await task
                if job.stop_requested:
                    await self.runner.stop(job_id)
                    if owned:
                        await asyncio.gather(*owned.values())
                        owned.clear()
                    current = self.require(job_id)
                    failure_reason = _queue_failure_reason(current)
                    await self._transition_job(
                        job_id,
                        "failed" if failure_reason is not None else "stopped",
                        reason=failure_reason or "Operator stopped execution",
                        stop_requested=False,
                    )
                    return
                if _successes(job) >= job.definition.stop.success_target:
                    if owned:
                        await self.storage.run(
                            self.store.set_job_state,
                            job_id,
                            "stopping",
                            stop_requested=True,
                            current_sample=job.current_sample,
                            terminal_reason="Verified success target reached",
                        )
                        await self.runner.stop(job_id)
                        await asyncio.gather(*owned.values())
                        owned.clear()
                    completed = await self.storage.run(
                        self.store.complete_success_target,
                        job_id,
                    )
                    await self._best_effort_notify(completed)
                    return
                terminal = _derived_terminal(job)
                if terminal is not None and not owned:
                    await self._transition_job(
                        job_id,
                        terminal,
                        reason=_terminal_reason(terminal),
                    )
                    return
                while len(owned) < job.concurrency:
                    job = self.require(job_id)
                    sample = _next_sample(job, frozenset(owned))
                    if sample is None:
                        break
                    if not _budget_slot_available(job, len(owned) + 1):
                        if not owned:
                            await self._transition_job(
                                job_id,
                                "failed",
                                reason=(
                                    "Confirmed budget cannot fund another "
                                    "bounded sample"
                                ),
                                launch_blocked=True,
                            )
                            return
                        break
                    run_id = sample.id
                    job = await self.storage.run(
                        self.store.claim_sample,
                        job_id,
                        sample.id,
                    )
                    await self._best_effort_notify(job)
                    if self.require(job_id).stop_requested:
                        cancelled = await self.storage.run(
                            self.store.finish_sample,
                            job_id,
                            sample.id,
                            SampleResult(
                                state="cancelled",
                                detail="Operator stop won the launch race",
                            ),
                            job_state="stopping",
                        )
                        await self._best_effort_notify(cancelled)
                        break
                    await self.storage.run(
                        self.store.set_sample_state,
                        job_id,
                        sample.id,
                        "running",
                        detail="Isolated benchmark process started",
                        run_id=run_id,
                    )
                    owned[sample.id] = asyncio.create_task(
                        self._execute_sample(job_id, sample.id, run_id),
                        name=f"experiment:{job_id}:{sample.id}",
                    )
                if owned:
                    await asyncio.wait(
                        tuple(owned.values()),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            await self.runner.stop(job_id)
            for task in owned.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*owned.values(), return_exceptions=True)
            await self._cancel_retained_active(
                job_id,
                "Executor cancelled after owned processes exited",
                interrupted=True,
            )
            current = self.require(job_id)
            if current.state not in TERMINAL_JOB_STATES:
                await self._transition_job(
                    job_id,
                    "stopped",
                    reason="Executor shutdown interrupted execution",
                    stop_requested=False,
                )
            raise
        except Exception as error:
            await self.runner.stop(job_id)
            await self._cancel_retained_active(
                job_id,
                f"Supervisor failure: {error}",
                interrupted=True,
            )
            current = self.require(job_id)
            if current.state not in TERMINAL_JOB_STATES:
                await self._transition_job(
                    job_id,
                    "failed",
                    reason=f"Supervisor failure: {error}",
                )
        finally:
            self.sample_tasks.pop(job_id, None)

    async def _execute_sample(
        self,
        job_id: str,
        sample_id: str,
        run_id: str,
    ) -> None:
        job = self.require(job_id)
        sample = job.samples[sample_id]
        try:
            result = await self.runner.run(job, sample)
        except asyncio.CancelledError:
            await self.storage.run(
                self.store.finish_sample,
                job_id,
                sample_id,
                SampleResult(
                    state="interrupted",
                    detail="Supervisor cancelled after process shutdown",
                ),
                job_state=None,
            )
            raise
        except Exception as error:
            result = SampleResult(
                state="setup_failure",
                detail=f"Runner failed: {error}",
            )
        current = self.require(job_id)
        if current.stop_requested:
            result = SampleResult(
                state="cancelled",
                detail="Operator stopped the running sample",
                cost_usd=result.cost_usd,
                turns=result.turns,
                calls=result.calls,
            )
        budget_exceeded = _result_exceeds_budget(current, result)
        if budget_exceeded:
            result = SampleResult(
                state="setup_failure",
                detail="Runner reported spend beyond the confirmed budget",
                cost_usd=result.cost_usd,
                turns=result.turns,
                calls=result.calls,
            )
        stop_queue = result.state == "setup_failure"
        failure_reason = (
            "Runner reported spend beyond an execution ceiling"
            if budget_exceeded
            else "Runner setup failure stopped the execution queue"
            if stop_queue
            else None
        )
        retained = await self.storage.run(
            self.store.finish_sample,
            job_id,
            sample_id,
            result,
            job_state=None,
            terminal_reason=failure_reason,
            launch_blocked=budget_exceeded,
            stop_requested=True if stop_queue else None,
        )
        await self._link_session(retained, sample_id, run_id)
        await self._best_effort_notify(self.require(job_id))

    async def _cancel_retained_active(
        self,
        job_id: str,
        reason: str,
        *,
        interrupted: bool = False,
    ) -> None:
        job = self.require(job_id)
        active = [
            sample
            for sample in job.samples.values()
            if sample.state in {"launching", "running"}
        ]
        for sample in active:
            state: ExperimentSampleState = "interrupted" if interrupted else "cancelled"
            await self.storage.run(
                self.store.finish_sample,
                job_id,
                sample.id,
                SampleResult(state=state, detail=reason),
                job_state=None,
            )

    async def _link_session(
        self,
        job: ExperimentJob,
        sample_id: str,
        run_id: str,
    ) -> None:
        if self.session_resolver is None:
            return
        resolved = self.session_resolver(job.id, run_id)
        session_id = await resolved if inspect.isawaitable(resolved) else resolved
        if session_id is None:
            return
        linked = await self.storage.run(
            self.store.link_session,
            job.id,
            sample_id,
            run_id=run_id,
            session_id=session_id,
        )
        await self._best_effort_notify(linked)

    async def _transition_job(
        self,
        job_id: str,
        state: ExperimentJobState,
        *,
        reason: str,
        stop_requested: bool | None = None,
        launch_blocked: bool | None = None,
    ) -> ExperimentJob:
        if state in TERMINAL_JOB_STATES:
            job = await self.storage.run(
                self.store.finalize_job,
                job_id,
                state,
                reason=reason,
                launch_blocked=launch_blocked,
            )
        else:
            job = await self.storage.run(
                self.store.set_job_state,
                job_id,
                state,
                current_sample=None,
                terminal_reason=reason,
                stop_requested=stop_requested,
                launch_blocked=launch_blocked,
            )
        await self._best_effort_notify(job)
        return job

    async def _notify(self, job: ExperimentJob) -> None:
        if self.observer is None:
            return
        result = self.observer(job)
        if inspect.isawaitable(result):
            await result

    async def _best_effort_notify(self, job: ExperimentJob) -> None:
        try:
            await self._notify(job)
        except Exception:
            return


def _successes(job: ExperimentJob) -> int:
    return sum(sample.state == "success" for sample in job.samples.values())


def _next_sample(
    job: ExperimentJob,
    owned: frozenset[str],
) -> ExperimentSample | None:
    return next(
        (
            sample
            for sample in sorted(
                job.samples.values(),
                key=lambda candidate: candidate.queue_position,
            )
            if sample.state == "queued" and sample.id not in owned
        ),
        None,
    )


def _derived_terminal(job: ExperimentJob) -> ExperimentJobState | None:
    if _successes(job) >= job.definition.stop.success_target:
        return "completed"
    if any(
        sample.state not in TERMINAL_SAMPLE_STATES for sample in job.samples.values()
    ):
        return None
    if any(
        sample.state in {"agent_failure", "setup_failure", "interrupted"}
        for sample in job.samples.values()
    ):
        return "failed"
    if all(
        sample.state in {"cancelled", "excluded"} for sample in job.samples.values()
    ):
        return "cancelled"
    return "failed"


def _terminal_reason(state: ExperimentJobState) -> str:
    if state == "completed":
        return "Verified success target reached"
    if state == "cancelled":
        return "Every retained sample was cancelled or excluded"
    return "Retained outcomes cannot reach the verified success target"


def _queue_failure_reason(job: ExperimentJob) -> str | None:
    if any(sample.state == "setup_failure" for sample in job.samples.values()):
        return job.terminal_reason or "Runner setup failure stopped the execution queue"
    return None


def _budget_slot_available(job: ExperimentJob, reserved_slots: int) -> bool:
    ceiling = min(
        job.confirmed_max_spend_usd,
        job.definition.stop.max_total_cost_usd,
    )
    reserved = reserved_slots * job.definition.per_sample_spend_ceiling_usd
    return not job.launch_blocked and job.spent_usd + reserved <= ceiling


def _result_exceeds_budget(job: ExperimentJob, result: SampleResult) -> bool:
    if result.cost_usd is None:
        return False
    return (
        result.cost_usd > job.definition.per_sample_spend_ceiling_usd
        or job.spent_usd + result.cost_usd
        > min(
            job.confirmed_max_spend_usd,
            job.definition.stop.max_total_cost_usd,
        )
    )
