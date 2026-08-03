"""Typed direct-argv experiment runner boundary."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from .execution_config import installed_models, validate_effective_config
from .models import (
    ExperimentJob,
    ExperimentSample,
    ExperimentSampleState,
    SampleResult,
)


class ExperimentRunner(Protocol):
    """One replaceable sample process boundary."""

    def dry_run(
        self,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> tuple[tuple[str, ...], Mapping[str, str]]:
        """Return safe argv and non-secret identity environment."""

    async def run(
        self,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> SampleResult:
        """Execute one retained sample."""

    async def stop(self, job_id: str) -> None:
        """Cooperatively terminate one owned sample process."""


class SubprocessExperimentRunner:
    """Run one isolated benchmark process per stable sample identity."""

    def __init__(
        self,
        *,
        benchmark_root: Path,
        repository_root: Path | None = None,
        terminate_timeout: float = 5.0,
    ) -> None:
        self.benchmark_root = benchmark_root.resolve()
        self.repository_root = (
            repository_root.resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[6]
        )
        if terminate_timeout <= 0:
            raise ValueError("terminate timeout must be positive")
        self.terminate_timeout = terminate_timeout
        self.processes: dict[
            tuple[str, str],
            asyncio.subprocess.Process,
        ] = {}
        self.installed_models = installed_models(self.repository_root)

    def dry_run(
        self,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> tuple[tuple[str, ...], Mapping[str, str]]:
        output = self._output(job, sample)
        config = sample.effective_config
        validate_effective_config(
            job.definition,
            config,
            repository_root=self.repository_root,
        )
        model = str(config.get("model.id", ""))
        if model not in self.installed_models:
            raise ValueError(f"model {model!r} is not in the installed catalog")
        configured_iterations = config.get(
            "policy.max_iterations",
            job.definition.stop.max_iterations_per_sample,
        )
        if isinstance(configured_iterations, bool) or not isinstance(
            configured_iterations, int
        ):
            raise ValueError("policy.max_iterations must be an integer")
        max_iterations = configured_iterations
        command = (
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
            str(config.get("render.mode", "full")),
            "--profile",
            str(config.get("tools.profile", "direct-full")),
            "--model",
            model,
            "--compaction-threshold",
            str(config.get("context.compaction_threshold", "")),
            "--journey",
            job.definition.journey,
            "--player-profile",
            job.player_profile,
            "--max-iterations",
            str(max_iterations),
            "--max-sample-cost",
            str(job.definition.per_sample_spend_ceiling_usd),
        )
        environment = {
            "BOUKENSHA_EXPERIMENT_ID": job.id,
            "BOUKENSHA_RUN_ID": sample.id,
        }
        return command, environment

    async def run(
        self,
        job: ExperimentJob,
        sample: ExperimentSample,
    ) -> SampleResult:
        output = self._output(job, sample)
        output.mkdir(parents=True, exist_ok=True)
        command, environment = self.dry_run(job, sample)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.repository_root,
            env={**os.environ, **environment},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        process_identity = (job.id, sample.id)
        self.processes[process_identity] = process
        try:
            return_code = await asyncio.wait_for(
                process.wait(),
                timeout=job.definition.stop.max_wall_seconds_per_sample,
            )
        except TimeoutError:
            await self._terminate(process)
            return SampleResult(
                state="setup_failure",
                detail="Sample exceeded the wall-time stop criterion",
            )
        finally:
            if self.processes.get(process_identity) is process:
                self.processes.pop(process_identity, None)
        record = _result_record(output / "attempts.jsonl")
        if record is None:
            return SampleResult(
                state="setup_failure",
                detail=f"Runner exited {return_code} without an attempt record",
            )
        if record.get("setup_failure"):
            state: ExperimentSampleState = "setup_failure"
        elif record.get("success"):
            state = "success"
        else:
            state = "agent_failure"
        return SampleResult(
            state=state,
            detail=str(record.get("error") or record.get("stop_reason") or state),
            cost_usd=_optional_float(record.get("cost_usd")),
            turns=_optional_int(record.get("iterations")),
            calls=_optional_int(record.get("tool_calls")),
        )

    async def stop(self, job_id: str) -> None:
        owned = tuple(
            process
            for (candidate_job_id, _sample_id), process in self.processes.items()
            if candidate_job_id == job_id
        )
        await asyncio.gather(
            *(self._terminate(process) for process in owned),
            return_exceptions=False,
        )

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        """TERM, bounded wait, then verified process-group escalation."""
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            await process.wait()
            return
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self.terminate_timeout,
            )
            return
        except TimeoutError:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self.terminate_timeout,
            )
        except TimeoutError as error:
            raise RuntimeError("owned experiment process did not exit") from error

    def _output(self, job: ExperimentJob, sample: ExperimentSample) -> Path:
        return self.benchmark_root / f"observatory-{job.id}-{sample.id}"


def _result_record(path: Path) -> dict[str, object] | None:
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


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None
