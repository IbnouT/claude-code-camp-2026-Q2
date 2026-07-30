"""Confirmed, budgeted experiment job execution with deterministic resume."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ExperimentDefinition
from .experiments import sample_queue
from .sources.benchmark import stable_run_id


class ExperimentRequestConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


@dataclass
class ExperimentJob:
    """Mutable runtime state persisted after every transition."""

    id: str
    request_id: str
    player_profile: str
    definition: ExperimentDefinition
    confirmed_max_spend_usd: float
    state: str = "queued"
    spent_usd: float = 0
    current_sample: str | None = None
    stop_requested: bool = False
    samples: dict[str, dict[str, Any]] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "player_profile": self.player_profile,
            "definition_id": self.definition.id,
            "definition": self.definition.model_dump(mode="json"),
            "state": self.state,
            "confirmed_max_spend_usd": self.confirmed_max_spend_usd,
            "spent_usd": self.spent_usd,
            "current_sample": self.current_sample,
            "samples": list(self.samples.values()),
        }


class ExperimentExecutor:
    """Run one isolated benchmark process per stable sample identity."""

    def __init__(
        self,
        state_root: Path,
        *,
        benchmark_root: Path,
        repository_root: Path | None = None,
    ) -> None:
        self.state_root = state_root.resolve()
        self.benchmark_root = benchmark_root.resolve()
        self.repository_root = (
            repository_root.resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[3]
        )
        self.jobs: dict[str, ExperimentJob] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self._load()

    def create(
        self,
        *,
        request_id: str,
        definition: ExperimentDefinition,
        player_profile: str,
        confirmed_max_spend_usd: float,
    ) -> ExperimentJob:
        for job in self.jobs.values():
            if job.request_id == request_id:
                if (
                    job.definition != definition
                    or job.player_profile != player_profile
                    or job.confirmed_max_spend_usd != confirmed_max_spend_usd
                ):
                    raise ExperimentRequestConflict(
                        "The request id already belongs to a different "
                        "experiment definition, player, or spend confirmation."
                    )
                return job
        job_id = _safe_id(request_id)
        if job_id in self.jobs:
            suffix = 2
            while f"{job_id}-{suffix}" in self.jobs:
                suffix += 1
            job_id = f"{job_id}-{suffix}"
        queue = sample_queue(definition)
        arms = {
            arm.id: arm
            for arm in definition.arms
        }
        samples: dict[str, dict[str, Any]] = {}
        for sample_id in queue:
            arm_id, ordinal = _sample_parts(sample_id)
            samples[sample_id] = {
                "id": sample_id,
                "arm_id": arm_id,
                "ordinal": ordinal,
                "state": "queued",
                "run_id": None,
                "cost_usd": None,
                "turns": None,
                "calls": None,
                "detail": "Waiting for execution",
                "effective_config": arms[arm_id].values,
            }
        job = ExperimentJob(
            id=job_id,
            request_id=request_id,
            player_profile=player_profile,
            definition=definition,
            confirmed_max_spend_usd=confirmed_max_spend_usd,
            samples=samples,
        )
        self.jobs[job.id] = job
        self.persist_definition(definition)
        self._persist(job)
        return job

    def persist_definition(self, definition: ExperimentDefinition) -> Path:
        """Store an immutable, secret-free definition beside runtime jobs."""

        target = (
            self.state_root
            / "definitions"
            / f"{_safe_id(definition.id)}-v{definition.version}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != definition.model_dump(mode="json"):
                raise ValueError(
                    "An immutable experiment definition already uses this id and version."
                )
            return target
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                definition.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def start(self, job_id: str) -> ExperimentJob:
        job = self.require(job_id)
        active = self.tasks.get(job_id)
        if active is not None and not active.done():
            return job
        job.stop_requested = False
        job.state = "running"
        self._persist(job)
        self.tasks[job_id] = asyncio.create_task(self._run(job))
        return job

    async def stop(self, job_id: str) -> ExperimentJob:
        job = self.require(job_id)
        job.stop_requested = True
        job.state = "stopping"
        process = self.processes.get(job_id)
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._persist(job)
        return job

    def require(self, job_id: str) -> ExperimentJob:
        try:
            return self.jobs[job_id]
        except KeyError as error:
            raise KeyError(f"unknown experiment job {job_id!r}") from error

    async def _run(self, job: ExperimentJob) -> None:
        try:
            for sample in job.samples.values():
                if sample["state"] in {
                    "success",
                    "agent_failure",
                    "setup_failure",
                    "excluded",
                }:
                    continue
                if job.stop_requested:
                    job.state = "stopped"
                    break
                if _successes(job) >= job.definition.stop.success_target:
                    job.state = "completed"
                    break
                remaining = (
                    min(
                        job.confirmed_max_spend_usd,
                        job.definition.stop.max_total_cost_usd,
                    )
                    - job.spent_usd
                )
                if remaining < job.definition.per_sample_spend_ceiling_usd:
                    job.state = "stopped"
                    sample["detail"] = "Spend headroom is below the sample ceiling"
                    break
                await self._run_sample(job, sample)
                if sample["state"] == "setup_failure":
                    job.state = "stopped"
                    break
            else:
                job.state = "completed"
            if job.stop_requested:
                job.state = "stopped"
        except Exception as error:
            job.state = "failed"
            if job.current_sample:
                job.samples[job.current_sample]["detail"] = str(error)
        finally:
            job.current_sample = None
            self.processes.pop(job.id, None)
            self._persist(job)

    async def _run_sample(
        self,
        job: ExperimentJob,
        sample: dict[str, Any],
    ) -> None:
        sample_id = str(sample["id"])
        arm_id = str(sample["arm_id"])
        arm = next(arm for arm in job.definition.arms if arm.id == arm_id)
        result_mode = str(arm.values.get("render.mode", "full"))
        ledger_name = f"observatory-{job.id}-{sample_id}"
        output = self.benchmark_root / ledger_name
        output.mkdir(parents=True, exist_ok=True)
        command = self.sample_command(
            job=job,
            output=output,
            result_mode=result_mode,
            effective_config=arm.values,
        )
        sample["state"] = "running"
        sample["detail"] = "Reset and sample process started"
        job.current_sample = sample_id
        self._persist(job)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.repository_root,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes[job.id] = process
        try:
            return_code = await asyncio.wait_for(
                process.wait(),
                timeout=job.definition.stop.max_wall_seconds_per_sample,
            )
        except TimeoutError:
            os.killpg(process.pid, signal.SIGTERM)
            await process.wait()
            sample["state"] = "setup_failure"
            sample["detail"] = "Sample exceeded the wall-time stop criterion"
            return
        if job.stop_requested:
            sample["state"] = "queued"
            sample["detail"] = "Stopped by operator before a retained outcome"
            return
        record = _result_record(output / "attempts.jsonl")
        if record is None:
            sample["state"] = "setup_failure"
            sample["detail"] = f"Runner exited {return_code} without an attempt record"
            return
        cost = record.get("cost_usd")
        if isinstance(cost, int | float):
            sample["cost_usd"] = float(cost)
            job.spent_usd = round(job.spent_usd + float(cost), 8)
        sample["turns"] = _optional_int(record.get("iterations"))
        sample["calls"] = _optional_int(record.get("tool_calls"))
        attempt_id = record.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            sample["run_id"] = stable_run_id(ledger_name, attempt_id)
        if record.get("setup_failure"):
            sample["state"] = "setup_failure"
        elif record.get("success"):
            sample["state"] = "success"
        else:
            sample["state"] = "agent_failure"
        sample["detail"] = str(
            record.get("error")
            or record.get("stop_reason")
            or sample["state"]
        )
        self._persist(job)

    def sample_command(
        self,
        *,
        job: ExperimentJob,
        output: Path,
        result_mode: str,
        effective_config: dict[str, bool | int | float | str],
    ) -> tuple[str, ...]:
        """Build the direct-argv runner command without starting a process."""

        return (
            "uv",
            "run",
            "--project",
            str(self.repository_root / "week2_capable" / "benchmark"),
            "boukensha-e1",
            "--spend",
            "--cap",
            str(job.definition.per_sample_spend_ceiling_usd),
            "--runs",
            "1",
            "--output-dir",
            str(output),
            "--result-mode",
            result_mode,
            "--profile",
            str(effective_config.get("tools.profile", "direct-full")),
            "--model",
            str(effective_config.get("model.id", "")),
            "--compaction-threshold",
            str(effective_config.get("context.compaction_threshold", "")),
            "--journey",
            job.definition.journey,
            "--player-profile",
            job.player_profile,
            "--max-iterations",
            str(job.definition.stop.max_iterations_per_sample),
            "--max-sample-cost",
            str(job.definition.per_sample_spend_ceiling_usd),
        )

    def _persist(self, job: ExperimentJob) -> None:
        target = self.state_root / "jobs" / job.id / "job.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    **job.public(),
                    "stop_requested": job.stop_requested,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def _load(self) -> None:
        if not self.state_root.is_dir():
            return
        for path in self.state_root.glob("jobs/*/job.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                definition = ExperimentDefinition.model_validate(row["definition"])
                samples = {
                    sample["id"]: sample
                    for sample in row.get("samples", [])
                }
                job = ExperimentJob(
                    id=str(row["id"]),
                    request_id=str(row["request_id"]),
                    player_profile=str(row["player_profile"]),
                    definition=definition,
                    confirmed_max_spend_usd=float(
                        row["confirmed_max_spend_usd"]
                    ),
                    state=(
                        "stopped"
                        if row.get("state") in {"running", "stopping"}
                        else str(row.get("state", "stopped"))
                    ),
                    spent_usd=float(row.get("spent_usd", 0)),
                    samples=samples,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            self.jobs[job.id] = job


def _safe_id(request_id: str) -> str:
    cleaned = "".join(
        character.casefold()
        for character in request_id
        if character.isalnum() or character in {"-", "_"}
    ).strip("-_")
    return cleaned[:80] or "experiment-job"


def _sample_parts(sample_id: str) -> tuple[str, int]:
    arm_id, ordinal, _digest = sample_id.rsplit("-", 2)
    return arm_id, int(ordinal)


def _successes(job: ExperimentJob) -> int:
    return sum(sample["state"] == "success" for sample in job.samples.values())


def _result_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    rows = path.read_text(errors="replace").splitlines()
    if not rows:
        return None
    try:
        value = json.loads(rows[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    return None
