"""SQLite ownership for immutable definitions and durable experiment queues."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import ExperimentDefinition, ObservatoryQuery
from ..experiments import sample_queue
from .models import (
    ExperimentJob,
    ExperimentJobState,
    ExperimentSample,
    ExperimentSampleState,
    SampleResult,
)

SCHEMA_VERSION = 2

TERMINAL_JOB_STATES = frozenset({"completed", "failed", "cancelled"})
JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "stopped", "cancelled", "failed"}),
    "running": frozenset({"stopping", "stopped", "completed", "failed", "cancelled"}),
    "stopping": frozenset({"stopped", "completed", "failed", "cancelled"}),
    "stopped": frozenset({"running", "cancelled", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
SAMPLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"launching", "cancelled", "excluded"}),
    "launching": frozenset({"running", "setup_failure", "cancelled", "interrupted"}),
    "running": frozenset(
        {
            "success",
            "agent_failure",
            "setup_failure",
            "cancelled",
            "interrupted",
        }
    ),
    "success": frozenset(),
    "agent_failure": frozenset(),
    "setup_failure": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
    "excluded": frozenset(),
}


class ExperimentRequestConflict(ValueError):
    """An idempotency identity was reused with different input."""


class ExperimentDefinitionConflict(ValueError):
    """An immutable definition identity was reused with different content."""


class ExperimentStateConflict(ValueError):
    """A lifecycle transition violated the persisted state machine."""


class ExperimentIdentityConflict(ValueError):
    """A run or session identity conflicts with retained ownership."""


class ExperimentStore:
    """Own experiment identity, queue order, spend, and terminal outcomes."""

    def __init__(self, state_root: Path) -> None:
        root = state_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "experiments-v1.sqlite3"
        self._lock = threading.RLock()
        self._database = sqlite3.connect(
            self.path,
            timeout=2.0,
            check_same_thread=False,
        )
        self.path.chmod(0o600)
        self._database.row_factory = sqlite3.Row
        self._database.execute("PRAGMA busy_timeout = 2000")
        self._database.execute("PRAGMA foreign_keys = ON")
        self._database.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._database.close()

    def create(
        self,
        *,
        request_id: str,
        definition: ExperimentDefinition,
        player_profile: str,
        confirmed_max_spend_usd: float,
    ) -> tuple[ExperimentJob, bool]:
        definition = ExperimentDefinition.model_validate(
            definition.model_dump(mode="python")
        )
        if not math.isfinite(confirmed_max_spend_usd) or confirmed_max_spend_usd <= 0:
            raise ValueError("confirmed maximum spend must be finite and positive")
        if abs(confirmed_max_spend_usd - definition.effective_max_spend_usd) > 0.000001:
            raise ValueError(
                "confirmed maximum spend must equal the definition maximum"
            )
        payload = _definition_json(definition)
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                existing = self._database.execute(
                    "SELECT id FROM experiment_jobs WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if existing is not None:
                    job = self.get(str(existing["id"]))
                    if (
                        job.definition != definition
                        or job.player_profile != player_profile
                        or job.confirmed_max_spend_usd != confirmed_max_spend_usd
                    ):
                        raise ExperimentRequestConflict(
                            "The request id already belongs to different "
                            "experiment input."
                        )
                    self._database.commit()
                    return job, False
                definition_row = self._database.execute(
                    """
                    SELECT payload FROM experiment_definitions
                    WHERE id = ? AND version = ?
                    """,
                    (definition.id, definition.version),
                ).fetchone()
                if (
                    definition_row is not None
                    and str(definition_row["payload"]) != payload
                ):
                    raise ExperimentDefinitionConflict(
                        "An immutable experiment definition already uses this "
                        "id and version."
                    )
                now = _now()
                self._database.execute(
                    """
                    INSERT OR IGNORE INTO experiment_definitions (
                        id, version, payload, created_at, locked_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (definition.id, definition.version, payload, now, now),
                )
                self._database.execute(
                    """
                    UPDATE experiment_definitions
                    SET locked_at = COALESCE(locked_at, ?)
                    WHERE id = ? AND version = ?
                    """,
                    (now, definition.id, definition.version),
                )
                job_id = _safe_id(request_id)
                suffix = 2
                candidate = job_id
                while self._database.execute(
                    "SELECT 1 FROM experiment_jobs WHERE id = ?",
                    (candidate,),
                ).fetchone():
                    candidate = f"{job_id}-{suffix}"
                    suffix += 1
                job_id = candidate
                self._database.execute(
                    """
                    INSERT INTO experiment_jobs (
                        id, request_id, definition_id, definition_version,
                        player_profile, confirmed_max_spend_usd, state,
                        spent_usd, stop_requested, launch_blocked, terminal_reason,
                        concurrency, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, 0, 0, NULL, ?, ?, ?)
                    """,
                    (
                        job_id,
                        request_id,
                        definition.id,
                        definition.version,
                        player_profile,
                        confirmed_max_spend_usd,
                        definition.concurrency,
                        now,
                        now,
                    ),
                )
                arms = {arm.id: arm for arm in definition.arms}
                for position, sample_id in enumerate(sample_queue(definition)):
                    arm_id, ordinal = _sample_parts(sample_id)
                    self._database.execute(
                        """
                        INSERT INTO experiment_samples (
                            job_id, id, arm_id, ordinal, queue_position, state,
                            effective_config, detail
                        ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                        """,
                        (
                            job_id,
                            sample_id,
                            arm_id,
                            ordinal,
                            position,
                            json.dumps(arms[arm_id].values, sort_keys=True),
                            "Waiting for execution",
                        ),
                    )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
            return self.get(job_id), True

    def persist_definition(self, definition: ExperimentDefinition) -> None:
        payload = _definition_json(definition)
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                row = self._database.execute(
                    """
                    SELECT payload FROM experiment_definitions
                    WHERE id = ? AND version = ?
                    """,
                    (definition.id, definition.version),
                ).fetchone()
                if row is not None:
                    if str(row["payload"]) != payload:
                        raise ExperimentDefinitionConflict(
                            "An immutable experiment definition already uses "
                            "this id and version."
                        )
                    self._database.commit()
                    return
                now = _now()
                self._database.execute(
                    """
                    INSERT INTO experiment_definitions (
                        id, version, payload, created_at, locked_at
                    ) VALUES (?, ?, ?, ?, NULL)
                    """,
                    (definition.id, definition.version, payload, now),
                )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise

    def get(
        self,
        job_id: str,
        *,
        sample_after: int | None = None,
        sample_limit: int | None = None,
    ) -> ExperimentJob:
        with self._lock:
            row = self._database.execute(
                """
                SELECT j.*, d.payload AS definition_payload
                FROM experiment_jobs AS j
                JOIN experiment_definitions AS d
                  ON d.id = j.definition_id AND d.version = j.definition_version
                WHERE j.id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            clauses = ["job_id = ?"]
            arguments: list[object] = [job_id]
            if sample_after is not None:
                clauses.append("queue_position > ?")
                arguments.append(sample_after)
            limit_sql = ""
            if sample_limit is not None:
                if sample_limit < 0:
                    raise ValueError("sample limit must be nonnegative")
                limit_sql = " LIMIT ?"
                arguments.append(sample_limit)
            samples = self._database.execute(
                f"""
                SELECT * FROM experiment_samples
                WHERE {" AND ".join(clauses)}
                ORDER BY queue_position
                {limit_sql}
                """,
                arguments,
            ).fetchall()
        return _job(row, samples)

    def list_jobs(
        self,
        *,
        after_id: str | None = None,
        limit: int | None = None,
        include_samples: bool = True,
    ) -> tuple[ExperimentJob, ...]:
        with self._lock:
            clauses: list[str] = []
            arguments: list[object] = []
            if after_id is not None:
                clauses.append("id > ?")
                arguments.append(after_id)
            limit_sql = ""
            if limit is not None:
                if limit < 1:
                    raise ValueError("job limit must be positive")
                limit_sql = " LIMIT ?"
                arguments.append(limit)
            rows = self._database.execute(
                f"""
                SELECT id FROM experiment_jobs
                {"WHERE " + " AND ".join(clauses) if clauses else ""}
                ORDER BY id
                {limit_sql}
                """,
                arguments,
            ).fetchall()
        return tuple(
            self.get(
                str(row["id"]),
                sample_limit=None if include_samples else 0,
            )
            for row in rows
        )

    def list_definitions(
        self,
        *,
        after: tuple[str, int] | None = None,
        limit: int | None = None,
    ) -> tuple[ExperimentDefinition, ...]:
        with self._lock:
            clauses: list[str] = []
            arguments: list[object] = []
            if after is not None:
                clauses.append("(id, version) > (?, ?)")
                arguments.extend(after)
            limit_sql = ""
            if limit is not None:
                if limit < 1:
                    raise ValueError("definition limit must be positive")
                limit_sql = " LIMIT ?"
                arguments.append(limit)
            rows = self._database.execute(
                f"""
                SELECT payload FROM experiment_definitions
                {"WHERE " + " AND ".join(clauses) if clauses else ""}
                ORDER BY id, version
                {limit_sql}
                """,
                arguments,
            ).fetchall()
        return tuple(
            ExperimentDefinition.model_validate_json(str(row["payload"]))
            for row in rows
        )

    def list_samples(
        self,
        job_id: str,
        *,
        after_position: int | None,
        limit: int,
    ) -> tuple[ExperimentSample, ...]:
        if limit < 1:
            raise ValueError("sample limit must be positive")
        return tuple(
            self.get(
                job_id,
                sample_after=after_position,
                sample_limit=limit,
            ).samples.values()
        )

    def query_samples(
        self,
        job_id: str,
        query: ObservatoryQuery,
    ) -> tuple[ExperimentSample, ...]:
        """Fetch one bounded, filtered sample result directly from SQLite."""
        clauses = ["job_id = ?"]
        arguments: list[object] = [job_id]
        columns = {
            "arm_id": "arm_id",
            "state": "state",
            "cost_usd": "cost_usd",
        }
        for selected in query.filters:
            column = columns[selected.field]
            if selected.operator == "eq":
                clauses.append(f"{column} = ?")
                arguments.append(selected.value)
            elif selected.operator == "contains":
                clauses.append(
                    f"INSTR(LOWER(COALESCE(CAST({column} AS TEXT), 'None')), "
                    "LOWER(?)) > 0"
                )
                arguments.append(str(selected.value))
            else:
                comparator = ">=" if selected.operator == "gte" else "<="
                clauses.append(f"{column} IS NOT NULL AND {column} {comparator} ?")
                arguments.append(selected.value)
        order = (
            "COALESCE(cost_usd, 0.0) DESC, queue_position"
            if query.order == "cost_desc"
            else "queue_position"
        )
        arguments.append(query.limit)
        with self._lock:
            rows = self._database.execute(
                f"""
                SELECT * FROM experiment_samples
                WHERE {" AND ".join(clauses)}
                ORDER BY {order}
                LIMIT ?
                """,
                arguments,
            ).fetchall()
        return tuple(_sample(row) for row in rows)

    def sample_count(self, job_id: str) -> int:
        with self._lock:
            row = self._database.execute(
                "SELECT COUNT(*) AS count FROM experiment_samples WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def aggregates(self, job_id: str) -> dict[str, int | float]:
        with self._lock:
            rows = self._database.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM experiment_samples
                WHERE job_id = ?
                GROUP BY state
                """,
                (job_id,),
            ).fetchall()
            cost = self._database.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0) AS spent
                FROM experiment_samples
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        states = {str(row["state"]): int(row["count"]) for row in rows}
        return {
            "planned": sum(states.values()),
            "queued": states.get("queued", 0),
            "running": states.get("launching", 0) + states.get("running", 0),
            "success": states.get("success", 0),
            "failed": states.get("agent_failure", 0)
            + states.get("setup_failure", 0)
            + states.get("interrupted", 0),
            "cancelled": states.get("cancelled", 0),
            "excluded": states.get("excluded", 0),
            "spent_usd": round(0.0 if cost is None else float(cost["spent"]), 8),
        }

    def catalog_identity(self) -> dict[str, int | str]:
        """Summarize durable catalog content independently of page position."""
        with self._lock:
            jobs = self._database.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(MAX(updated_at), '') AS updated_at
                FROM experiment_jobs
                """
            ).fetchone()
            definitions = self._database.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(MAX(created_at), '') AS created_at,
                       COALESCE(MAX(locked_at), '') AS locked_at
                FROM experiment_definitions
                """
            ).fetchone()
        return {
            "job_count": 0 if jobs is None else int(jobs["count"]),
            "job_updated_at": "" if jobs is None else str(jobs["updated_at"]),
            "definition_count": (
                0 if definitions is None else int(definitions["count"])
            ),
            "definition_created_at": (
                "" if definitions is None else str(definitions["created_at"])
            ),
            "definition_locked_at": (
                "" if definitions is None else str(definitions["locked_at"])
            ),
        }

    def claim_sample(
        self,
        job_id: str,
        sample_id: str,
    ) -> ExperimentJob:
        """Atomically assign stable run identity before any process effect."""
        now = _now()
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                job = self._database.execute(
                    """
                    SELECT state, launch_blocked FROM experiment_jobs
                    WHERE id = ?
                    """,
                    (job_id,),
                ).fetchone()
                sample = self._database.execute(
                    """
                    SELECT state FROM experiment_samples
                    WHERE job_id = ? AND id = ?
                    """,
                    (job_id, sample_id),
                ).fetchone()
                if job is None:
                    raise KeyError(job_id)
                if sample is None:
                    raise KeyError(sample_id)
                if bool(job["launch_blocked"]):
                    raise ExperimentStateConflict("experiment launch is blocked")
                self._validate_job_transition(str(job["state"]), "running")
                self._validate_sample_transition(
                    str(sample["state"]),
                    "launching",
                )
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET state = 'launching', run_id = ?, detail = ?,
                        started_at = COALESCE(started_at, ?)
                    WHERE job_id = ? AND id = ?
                    """,
                    (
                        sample_id,
                        "Stable sample identity persisted before launch",
                        now,
                        job_id,
                        sample_id,
                    ),
                )
                self._database.execute(
                    """
                    UPDATE experiment_jobs
                    SET state = 'running', current_sample = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (sample_id, now, job_id),
                )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return self.get(job_id)

    def complete_success_target(self, job_id: str) -> ExperimentJob:
        """Exclude unneeded queued work before retaining completed status."""
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                job = self.get(job_id)
                if (
                    sum(sample.state == "success" for sample in job.samples.values())
                    < job.definition.stop.success_target
                ):
                    raise ExperimentStateConflict(
                        "success target has not been retained"
                    )
                if any(
                    sample.state in {"launching", "running"}
                    for sample in job.samples.values()
                ):
                    raise ExperimentStateConflict(
                        "active samples must exit before job completion"
                    )
                self._validate_job_transition(job.state, "completed")
                now = _now()
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET state = 'excluded',
                        detail = 'Excluded after verified success target',
                        finished_at = ?
                    WHERE job_id = ? AND state = 'queued'
                    """,
                    (now, job_id),
                )
                self._database.execute(
                    """
                    UPDATE experiment_jobs
                    SET state = 'completed', stop_requested = 0,
                        current_sample = NULL,
                        terminal_reason = 'Verified success target reached',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, job_id),
                )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return self.get(job_id)

    def finalize_job(
        self,
        job_id: str,
        state: ExperimentJobState,
        *,
        reason: str,
        launch_blocked: bool | None = None,
    ) -> ExperimentJob:
        """Make every sample explainable before a terminal job is visible."""
        if state not in TERMINAL_JOB_STATES:
            raise ValueError("finalize_job requires a terminal state")
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                job = self.get(job_id)
                if any(
                    sample.state in {"launching", "running"}
                    for sample in job.samples.values()
                ):
                    raise ExperimentStateConflict(
                        "active samples must exit before terminal job state"
                    )
                if (
                    state == "completed"
                    and sum(
                        sample.state == "success" for sample in job.samples.values()
                    )
                    < job.definition.stop.success_target
                ):
                    raise ExperimentStateConflict(
                        "completed job requires the retained success target"
                    )
                self._validate_job_transition(job.state, state)
                now = _now()
                queued_state = "cancelled" if state == "cancelled" else "excluded"
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET state = ?, detail = ?, finished_at = ?
                    WHERE job_id = ? AND state = 'queued'
                    """,
                    (queued_state, reason, now, job_id),
                )
                assignments = [
                    "state = ?",
                    "stop_requested = 0",
                    "current_sample = NULL",
                    "terminal_reason = ?",
                    "updated_at = ?",
                ]
                values: list[object] = [state, reason, now]
                if launch_blocked is not None:
                    assignments.append(
                        "launch_blocked = CASE WHEN launch_blocked = 1 OR ? = 1 "
                        "THEN 1 ELSE 0 END"
                    )
                    values.append(int(launch_blocked))
                values.append(job_id)
                self._database.execute(
                    f"""
                    UPDATE experiment_jobs
                    SET {", ".join(assignments)}
                    WHERE id = ?
                    """,
                    values,
                )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return self.get(job_id)

    def set_job_state(
        self,
        job_id: str,
        state: ExperimentJobState,
        *,
        stop_requested: bool | None = None,
        current_sample: str | None = None,
        terminal_reason: str | None = None,
        launch_blocked: bool | None = None,
    ) -> ExperimentJob:
        if state in TERMINAL_JOB_STATES:
            raise ExperimentStateConflict("terminal job states require finalize_job")
        assignments = ["state = ?", "current_sample = ?", "updated_at = ?"]
        values: list[object] = [state, current_sample, _now()]
        if stop_requested is not None:
            assignments.append("stop_requested = ?")
            values.append(int(stop_requested))
        if terminal_reason is not None:
            assignments.append("terminal_reason = ?")
            values.append(terminal_reason)
        if launch_blocked is not None:
            assignments.append("launch_blocked = ?")
            values.append(int(launch_blocked))
        values.append(job_id)
        with self._lock:
            current = self._database.execute(
                "SELECT state FROM experiment_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if current is None:
                raise KeyError(job_id)
            self._validate_job_transition(str(current["state"]), state)
            self._database.execute(
                f"UPDATE experiment_jobs SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            self._database.commit()
        return self.get(job_id)

    def set_sample_state(
        self,
        job_id: str,
        sample_id: str,
        state: ExperimentSampleState,
        *,
        detail: str,
        run_id: str | None = None,
    ) -> ExperimentJob:
        now = _now()
        started_at = now if state in {"launching", "running"} else None
        finished_at = (
            now
            if state
            in {
                "success",
                "agent_failure",
                "setup_failure",
                "cancelled",
                "interrupted",
                "excluded",
            }
            else None
        )
        with self._lock:
            current = self._database.execute(
                """
                SELECT state, started_at, run_id FROM experiment_samples
                WHERE job_id = ? AND id = ?
                """,
                (job_id, sample_id),
            ).fetchone()
            if current is None:
                raise KeyError(sample_id)
            self._validate_sample_transition(str(current["state"]), state)
            self._database.execute(
                """
                UPDATE experiment_samples
                SET state = ?, detail = ?, run_id = ?,
                    started_at = COALESCE(started_at, ?),
                    finished_at = COALESCE(?, finished_at)
                WHERE job_id = ? AND id = ?
                """,
                (
                    state,
                    detail,
                    run_id if run_id is not None else current["run_id"],
                    started_at,
                    finished_at,
                    job_id,
                    sample_id,
                ),
            )
            self._touch(job_id)
            self._database.commit()
        return self.get(job_id)

    @staticmethod
    def _validate_job_transition(current: str, target: str) -> None:
        if current == target:
            return
        allowed = JOB_TRANSITIONS.get(current)
        if allowed is None or target not in allowed:
            raise ExperimentStateConflict(
                f"experiment job cannot transition from {current} to {target}"
            )

    @staticmethod
    def _validate_sample_transition(current: str, target: str) -> None:
        if current == target:
            return
        allowed = SAMPLE_TRANSITIONS.get(current)
        if allowed is None or target not in allowed:
            raise ExperimentStateConflict(
                f"experiment sample cannot transition from {current} to {target}"
            )

    def record_result(
        self,
        job_id: str,
        sample_id: str,
        result: SampleResult,
    ) -> ExperimentJob:
        return self.finish_sample(
            job_id,
            sample_id,
            result,
            job_state=None,
        )

    def finish_sample(
        self,
        job_id: str,
        sample_id: str,
        result: SampleResult,
        *,
        job_state: ExperimentJobState | None,
        terminal_reason: str | None = None,
        launch_blocked: bool = False,
        stop_requested: bool | None = None,
    ) -> ExperimentJob:
        """Atomically retain a terminal sample before updating its owning job."""
        self._validate_result(result)
        with self._lock:
            now = _now()
            self._database.execute("BEGIN IMMEDIATE")
            try:
                current_sample = self._database.execute(
                    """
                    SELECT state FROM experiment_samples
                    WHERE job_id = ? AND id = ?
                    """,
                    (job_id, sample_id),
                ).fetchone()
                if current_sample is None:
                    raise KeyError(sample_id)
                current_job = self._database.execute(
                    "SELECT state FROM experiment_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if current_job is None:
                    raise KeyError(job_id)
                self._validate_sample_transition(
                    str(current_sample["state"]),
                    result.state,
                )
                selected_job_state = (
                    str(current_job["state"]) if job_state is None else job_state
                )
                if stop_requested is True and selected_job_state == "running":
                    selected_job_state = "stopping"
                self._validate_job_transition(
                    str(current_job["state"]),
                    selected_job_state,
                )
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET state = ?, detail = ?, cost_usd = ?, turns = ?, calls = ?,
                        finished_at = ?
                    WHERE job_id = ? AND id = ?
                    """,
                    (
                        result.state,
                        result.detail,
                        result.cost_usd,
                        result.turns,
                        result.calls,
                        now,
                        job_id,
                        sample_id,
                    ),
                )
                spend = self._sample_spend(job_id)
                assignments = [
                    "state = ?",
                    "spent_usd = ?",
                    "current_sample = NULL",
                    "updated_at = ?",
                ]
                values: list[object] = [selected_job_state, spend, now]
                if terminal_reason is not None:
                    assignments.append("terminal_reason = ?")
                    values.append(terminal_reason)
                if launch_blocked:
                    assignments.append("launch_blocked = 1")
                if stop_requested is not None:
                    assignments.append("stop_requested = ?")
                    values.append(int(stop_requested))
                values.append(job_id)
                self._database.execute(
                    f"""
                    UPDATE experiment_jobs
                    SET {", ".join(assignments)}
                    WHERE id = ?
                    """,
                    values,
                )
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return self.get(job_id)

    def reconcile_spend_and_budgets(self) -> tuple[ExperimentJob, ...]:
        """Rebuild spend from samples and permanently block retained overspend."""
        changed: list[str] = []
        with self._lock:
            rows = self._database.execute(
                """
                SELECT j.id, j.state, j.confirmed_max_spend_usd,
                       d.payload AS definition_payload
                FROM experiment_jobs AS j
                JOIN experiment_definitions AS d
                  ON d.id = j.definition_id AND d.version = j.definition_version
                ORDER BY j.id
                """
            ).fetchall()
            for row in rows:
                job_id = str(row["id"])
                definition = ExperimentDefinition.model_validate_json(
                    str(row["definition_payload"])
                )
                metrics = self._database.execute(
                    """
                    SELECT cost_usd, turns, calls
                    FROM experiment_samples
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchall()
                invalid_metrics = any(
                    _invalid_retained_metric(metric[name])
                    for metric in metrics
                    for name in ("cost_usd", "turns", "calls")
                )
                spend = self._sample_spend(job_id)
                per_sample_over = self._database.execute(
                    """
                    SELECT 1 FROM experiment_samples
                    WHERE job_id = ? AND cost_usd > ?
                    LIMIT 1
                    """,
                    (job_id, definition.per_sample_spend_ceiling_usd),
                ).fetchone()
                total_ceiling = min(
                    float(row["confirmed_max_spend_usd"]),
                    definition.stop.max_total_cost_usd,
                )
                blocked = (
                    invalid_metrics
                    or not math.isfinite(spend)
                    or per_sample_over is not None
                    or spend > total_ceiling
                )
                selected_state = str(row["state"])
                if blocked:
                    selected_state = "failed"
                now = _now()
                if blocked:
                    self._database.execute(
                        """
                        UPDATE experiment_samples
                        SET state = 'excluded',
                            detail =
                                'Retained spend exceeds an execution ceiling',
                            finished_at = ?
                        WHERE job_id = ? AND state = 'queued'
                        """,
                        (now, job_id),
                    )
                self._database.execute(
                    """
                    UPDATE experiment_jobs
                    SET spent_usd = ?, launch_blocked = CASE
                            WHEN launch_blocked = 1 OR ? = 1 THEN 1 ELSE 0 END,
                        state = ?,
                        terminal_reason = CASE
                            WHEN ? = 1 THEN
                                'Retained spend exceeds an execution ceiling'
                            ELSE terminal_reason
                        END,
                        current_sample = CASE WHEN ? = 1 THEN NULL
                                              ELSE current_sample END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        spend,
                        int(blocked),
                        selected_state,
                        int(blocked),
                        int(blocked),
                        now,
                        job_id,
                    ),
                )
                changed.append(job_id)
            self._database.commit()
        return tuple(self.get(job_id) for job_id in changed)

    def _sample_spend(self, job_id: str) -> float:
        row = self._database.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS spent
            FROM experiment_samples
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        return round(0.0 if row is None else float(row["spent"]), 8)

    @staticmethod
    def _validate_result(result: SampleResult) -> None:
        for name, value in (
            ("cost_usd", result.cost_usd),
            ("turns", result.turns),
            ("calls", result.calls),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be nonnegative")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

    def link_session(
        self,
        job_id: str,
        sample_id: str,
        *,
        run_id: str,
        session_id: str,
    ) -> ExperimentJob:
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                current = self._database.execute(
                    """
                    SELECT run_id, session_id FROM experiment_samples
                    WHERE job_id = ? AND id = ?
                    """,
                    (job_id, sample_id),
                ).fetchone()
                if current is None:
                    raise KeyError(sample_id)
                if current["run_id"] not in {None, run_id}:
                    raise ExperimentIdentityConflict(
                        "sample run identity cannot be replaced"
                    )
                if current["session_id"] not in {None, session_id}:
                    raise ExperimentIdentityConflict(
                        "canonical session identity conflicts with retained evidence"
                    )
                conflict = self._database.execute(
                    """
                    SELECT id FROM experiment_samples
                    WHERE job_id = ? AND run_id = ? AND id != ?
                    """,
                    (job_id, run_id, sample_id),
                ).fetchone()
                if conflict is not None:
                    raise ExperimentIdentityConflict(
                        "run identity is already linked to another sample"
                    )
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET run_id = ?, session_id = ?
                    WHERE job_id = ? AND id = ?
                    """,
                    (run_id, session_id, job_id, sample_id),
                )
                self._touch(job_id)
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return self.get(job_id)

    def samples_with_run_identity(
        self,
    ) -> tuple[tuple[str, str, str, str | None], ...]:
        with self._lock:
            rows = self._database.execute(
                """
                SELECT job_id, id, run_id, session_id
                FROM experiment_samples
                WHERE run_id IS NOT NULL
                ORDER BY job_id, queue_position
                """
            ).fetchall()
        return tuple(
            (
                str(row["job_id"]),
                str(row["id"]),
                str(row["run_id"]),
                None if row["session_id"] is None else str(row["session_id"]),
            )
            for row in rows
        )

    def reconcile_interrupted(self) -> tuple[ExperimentJob, ...]:
        """Stop uncertain work without ever launching it a second time."""
        with self._lock:
            rows = self._database.execute(
                """
                SELECT id AS job_id FROM experiment_jobs
                WHERE state IN ('running', 'stopping')
                ORDER BY id
                """
            ).fetchall()
            now = _now()
            for row in rows:
                job_id = str(row["job_id"])
                self._database.execute("BEGIN IMMEDIATE")
                self._database.execute(
                    """
                    UPDATE experiment_samples
                    SET state = 'interrupted',
                        detail = 'Interrupted during reconciliation; not relaunched',
                        finished_at = ?
                    WHERE job_id = ? AND state IN ('launching', 'running')
                    """,
                    (now, job_id),
                )
                self._database.execute(
                    """
                    UPDATE experiment_jobs
                    SET state = 'stopped', stop_requested = 0,
                        current_sample = NULL,
                        terminal_reason =
                            'Recovered after an interrupted owned process',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, job_id),
                )
                self._database.commit()
        return tuple(self.get(str(row["job_id"])) for row in rows)

    def replace_for_compatibility(self, job: ExperimentJob) -> None:
        """Persist explicitly mutated compatibility objects used by old callers."""
        with self._lock:
            self._database.execute(
                """
                UPDATE experiment_jobs
                SET state = ?, spent_usd = ?, current_sample = ?,
                    stop_requested = ?, launch_blocked = ?,
                    terminal_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    job.state,
                    job.spent_usd,
                    job.current_sample,
                    int(job.stop_requested),
                    int(job.launch_blocked),
                    job.terminal_reason,
                    _now(),
                    job.id,
                ),
            )
            self._database.commit()

    def _touch(self, job_id: str) -> None:
        self._database.execute(
            "UPDATE experiment_jobs SET updated_at = ? WHERE id = ?",
            (_now(), job_id),
        )

    def _migrate(self) -> None:
        with self._lock:
            self._database.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment_schema (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_definitions (
                    id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    locked_at TEXT,
                    PRIMARY KEY (id, version)
                );
                CREATE TABLE IF NOT EXISTS experiment_jobs (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    definition_id TEXT NOT NULL,
                    definition_version INTEGER NOT NULL,
                    player_profile TEXT NOT NULL,
                    confirmed_max_spend_usd REAL NOT NULL,
                    state TEXT NOT NULL,
                    spent_usd REAL NOT NULL,
                    current_sample TEXT,
                    stop_requested INTEGER NOT NULL,
                    launch_blocked INTEGER NOT NULL DEFAULT 0,
                    terminal_reason TEXT,
                    concurrency INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (definition_id, definition_version)
                      REFERENCES experiment_definitions(id, version)
                );
                CREATE TABLE IF NOT EXISTS experiment_samples (
                    job_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    arm_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    queue_position INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    run_id TEXT,
                    session_id TEXT,
                    cost_usd REAL,
                    turns INTEGER,
                    calls INTEGER,
                    detail TEXT NOT NULL,
                    effective_config TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    PRIMARY KEY (job_id, id),
                    UNIQUE (job_id, queue_position),
                    UNIQUE (job_id, run_id),
                    FOREIGN KEY (job_id) REFERENCES experiment_jobs(id)
                );
                CREATE INDEX IF NOT EXISTS experiment_jobs_definition
                ON experiment_jobs(definition_id, created_at, id);
                CREATE INDEX IF NOT EXISTS experiment_jobs_page
                ON experiment_jobs(id);
                CREATE INDEX IF NOT EXISTS experiment_definitions_page
                ON experiment_definitions(id, version);
                CREATE INDEX IF NOT EXISTS experiment_samples_state
                ON experiment_samples(job_id, state, queue_position);
                CREATE INDEX IF NOT EXISTS experiment_samples_page
                ON experiment_samples(job_id, queue_position, id);
                """
            )
            row = self._database.execute(
                "SELECT version FROM experiment_schema"
            ).fetchone()
            if row is None:
                self._database.execute(
                    "INSERT INTO experiment_schema(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) == 1:
                columns = {
                    str(item["name"])
                    for item in self._database.execute(
                        "PRAGMA table_info(experiment_jobs)"
                    ).fetchall()
                }
                if "launch_blocked" not in columns:
                    self._database.execute(
                        """
                        ALTER TABLE experiment_jobs
                        ADD COLUMN launch_blocked INTEGER NOT NULL DEFAULT 0
                        """
                    )
                if "terminal_reason" not in columns:
                    self._database.execute(
                        "ALTER TABLE experiment_jobs ADD COLUMN terminal_reason TEXT"
                    )
                self._database.execute(
                    "UPDATE experiment_schema SET version = ?",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported experiment store schema")
            self._database.commit()


def _job(row: sqlite3.Row, sample_rows: list[sqlite3.Row]) -> ExperimentJob:
    samples = {str(sample["id"]): _sample(sample) for sample in sample_rows}
    return ExperimentJob(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        player_profile=str(row["player_profile"]),
        definition=ExperimentDefinition.model_validate_json(
            str(row["definition_payload"])
        ),
        confirmed_max_spend_usd=float(row["confirmed_max_spend_usd"]),
        state=str(row["state"]),  # type: ignore[arg-type]
        spent_usd=float(row["spent_usd"]),
        current_sample=(
            None if row["current_sample"] is None else str(row["current_sample"])
        ),
        stop_requested=bool(row["stop_requested"]),
        launch_blocked=bool(row["launch_blocked"]),
        terminal_reason=(
            None if row["terminal_reason"] is None else str(row["terminal_reason"])
        ),
        concurrency=int(row["concurrency"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        samples=samples,
    )


def _sample(row: sqlite3.Row) -> ExperimentSample:
    return ExperimentSample(
        id=str(row["id"]),
        arm_id=str(row["arm_id"]),
        ordinal=int(row["ordinal"]),
        queue_position=int(row["queue_position"]),
        state=str(row["state"]),  # type: ignore[arg-type]
        effective_config=json.loads(str(row["effective_config"])),
        run_id=None if row["run_id"] is None else str(row["run_id"]),
        session_id=None if row["session_id"] is None else str(row["session_id"]),
        cost_usd=None if row["cost_usd"] is None else float(row["cost_usd"]),
        turns=None if row["turns"] is None else int(row["turns"]),
        calls=None if row["calls"] is None else int(row["calls"]),
        detail=str(row["detail"]),
        started_at=None if row["started_at"] is None else str(row["started_at"]),
        finished_at=(None if row["finished_at"] is None else str(row["finished_at"])),
    )


def _definition_json(definition: ExperimentDefinition) -> str:
    return json.dumps(
        definition.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _invalid_retained_metric(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool) or not isinstance(value, int | float):
        return True
    return value < 0 or not math.isfinite(float(value))
