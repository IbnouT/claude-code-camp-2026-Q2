"""Bounded experiment catalog and sample resources."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from ..contracts import ExperimentDefinition
from ..database import open_readonly_database
from ..experiment_jobs.models import ExperimentSample
from .base import ResourceBase, ResourceNotFoundError, validate_limit
from .bounds import content_identity
from .contracts import (
    ExperimentCatalogPage,
    ExperimentDefinitionSummary,
    ExperimentDetailResponse,
    ExperimentJobSummary,
    ExperimentSampleSummary,
    ExperimentSummary,
)
from .cursor import CursorCoordinates, decode_cursor, encode_cursor


class ExperimentResources(ResourceBase):
    """Read registry-owned correlations and indexed sample summaries."""

    def experiment_catalog(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> ExperimentCatalogPage:
        validate_limit(limit, maximum=50)
        resource_id = "experiment-catalog"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        after_experiment = None if after is None else after.primary or None
        cursor_dimensions = (
            {} if after is None or not after.secondary else json.loads(after.secondary)
        )
        if not isinstance(cursor_dimensions, dict):
            raise ValueError("experiment catalog cursor dimensions are invalid")
        after_definition = cursor_dimensions.get("definition")
        after_job = cursor_dimensions.get("job")
        if after_definition is not None and not isinstance(after_definition, str):
            raise ValueError("definition cursor must be text")
        if after_job is not None and not isinstance(after_job, str):
            raise ValueError("job cursor must be text")
        clauses = ["experiment_id IS NOT NULL", "run_id IS NOT NULL"]
        arguments: list[object] = []
        if after_experiment is not None:
            clauses.append("experiment_id > ?")
            arguments.append(after_experiment)
        arguments.append(limit + 1)
        with open_readonly_database(self.registry.source) as database:
            rows = database.execute(
                f"""
                SELECT experiment_id, COUNT(*) AS sample_count,
                       COUNT(DISTINCT session_id) AS session_count,
                       MAX(updated_at) AS latest_session_at
                FROM sessions
                WHERE {" AND ".join(clauses)}
                GROUP BY experiment_id
                ORDER BY experiment_id
                LIMIT ?
                """,
                arguments,
            ).fetchall()
            aggregate = database.execute(
                """
                SELECT COUNT(DISTINCT experiment_id) AS experiments,
                       COUNT(*) AS samples,
                       COALESCE(MAX(updated_at), '') AS updated_at
                FROM sessions
                WHERE experiment_id IS NOT NULL AND run_id IS NOT NULL
                """
            ).fetchone()
        retained_experiments = tuple(
            ExperimentSummary(
                experiment_id=str(row["experiment_id"]),
                sample_count=int(row["sample_count"]),
                session_count=int(row["session_count"]),
                latest_session_at=str(row["latest_session_at"]),
            )
            for row in rows
        )
        store = getattr(self, "experiment_store", None)
        durable_experiment_jobs = (
            ()
            if store is None
            else store.list_jobs(
                after_id=after_experiment,
                limit=limit + 1,
                include_samples=False,
            )
        )
        durable_jobs_page = (
            ()
            if store is None
            else store.list_jobs(
                after_id=after_job,
                limit=limit + 1,
                include_samples=False,
            )
        )
        durable_by_id = {job.id: job for job in durable_experiment_jobs}
        retained_by_id = {
            experiment.experiment_id: experiment for experiment in retained_experiments
        }
        experiment_ids = sorted(
            experiment_id
            for experiment_id in set(retained_by_id) | set(durable_by_id)
            if after_experiment is None or experiment_id > after_experiment
        )
        visible_ids = experiment_ids[:limit]
        experiments = tuple(
            (
                retained_by_id[experiment_id]
                if experiment_id in retained_by_id
                else ExperimentSummary(
                    experiment_id=experiment_id,
                    sample_count=(
                        0 if store is None else store.sample_count(experiment_id)
                    ),
                    session_count=0,
                    latest_session_at="",
                )
            )
            for experiment_id in visible_ids
        )
        definition_after_parts = _definition_cursor_parts(after_definition)
        durable_definitions = (
            ()
            if store is None
            else store.list_definitions(
                after=definition_after_parts,
                limit=limit + 1,
            )
        )
        visible_definitions = durable_definitions[:limit]
        definitions = tuple(
            ExperimentDefinitionSummary(
                id=f"{definition.id}:v{definition.version}",
                values=definition.model_dump(mode="json"),
            )
            for definition in visible_definitions
        )
        visible_jobs = durable_jobs_page[:limit]
        jobs = tuple(
            ExperimentJobSummary(
                id=job.id,
                state=job.state,
                values={
                    "definition_id": job.definition.id,
                    "definition_version": job.definition.version,
                    "player_profile": job.player_profile,
                    "spent_usd": job.spent_usd,
                    "confirmed_max_spend_usd": job.confirmed_max_spend_usd,
                    "current_sample": job.current_sample,
                    "aggregates": (
                        job.aggregates() if store is None else store.aggregates(job.id)
                    ),
                },
            )
            for job in visible_jobs
        )
        more_experiments = len(experiment_ids) > limit
        more_definitions = len(durable_definitions) > limit
        more_jobs = len(durable_jobs_page) > limit
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=(
                        experiments[-1].experiment_id
                        if experiments
                        else after_experiment or ""
                    ),
                    secondary=json.dumps(
                        {
                            "definition": (
                                _definition_cursor(visible_definitions[-1])
                                if visible_definitions
                                else after_definition
                            ),
                            "job": (visible_jobs[-1].id if visible_jobs else after_job),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                )
            )
            if more_experiments or more_definitions or more_jobs
            else None
        )
        identity = {
            "experiments": 0 if aggregate is None else int(aggregate["experiments"]),
            "samples": 0 if aggregate is None else int(aggregate["samples"]),
            "updated_at": "" if aggregate is None else str(aggregate["updated_at"]),
            "durable": {} if store is None else store.catalog_identity(),
        }
        version, source_cursor = content_identity("obe1", identity)
        return ExperimentCatalogPage(
            resource_id=resource_id,
            resource_version=version,
            source_cursor=source_cursor,
            completeness="complete" if store is not None else "partial",
            capture_gaps=(
                ()
                if store is not None
                else (
                    "experiment_definitions_unavailable",
                    "experiment_jobs_unavailable",
                )
            ),
            source_refs=(
                "registry.db experiment correlations",
                *(
                    ()
                    if store is None
                    else ("experiments-v1.sqlite3 definitions and jobs",)
                ),
            ),
            continuation_cursor=continuation,
            experiments=experiments,
            definitions=definitions,
            jobs=jobs,
        )

    def experiment_detail(
        self,
        experiment_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> ExperimentDetailResponse:
        validate_limit(limit, maximum=100)
        resource_id = f"experiment:{experiment_id}"
        after = None if cursor is None else decode_cursor(cursor, resource=resource_id)
        store = getattr(self, "experiment_store", None)
        durable_job = None
        if store is not None:
            try:
                durable_job = store.get(experiment_id, sample_limit=0)
            except KeyError:
                durable_job = None
        durable_page: tuple[ExperimentSample, ...] = ()
        if durable_job is not None:
            assert store is not None
            after_position = None if after is None else int(after.primary)
            durable_page = store.list_samples(
                experiment_id,
                after_position=after_position,
                limit=limit + 1,
            )
            run_ids = tuple(
                sample.run_id
                for sample in durable_page[:limit]
                if sample.run_id is not None
            )
            clauses = ["experiment_id = ?", "run_id IS NOT NULL"]
            arguments: list[object] = [experiment_id]
            if run_ids:
                placeholders = ",".join("?" for _run_id in run_ids)
                clauses.append(f"run_id IN ({placeholders})")
                arguments.extend(run_ids)
            else:
                clauses.append("0 = 1")
            query_limit = limit + 1
        else:
            clauses = ["experiment_id = ?", "run_id IS NOT NULL"]
            arguments = [experiment_id]
            if after is not None:
                clauses.append("(run_id, session_id) > (?, ?)")
                arguments.extend((after.primary, after.secondary))
            query_limit = limit + 1
        arguments.append(query_limit)
        with open_readonly_database(self.registry.source) as database:
            rows = database.execute(
                f"""
                SELECT run_id, session_id, player_id, state, updated_at
                FROM sessions
                WHERE {" AND ".join(clauses)}
                ORDER BY run_id, session_id
                LIMIT ?
                """,
                arguments,
            ).fetchall()
            aggregate = database.execute(
                """
                SELECT COUNT(*) AS samples,
                       COUNT(DISTINCT session_id) AS sessions,
                       COALESCE(MAX(updated_at), '') AS updated_at
                FROM sessions
                WHERE experiment_id = ? AND run_id IS NOT NULL
                """,
                (experiment_id,),
            ).fetchone()
        with closing(self._connect()) as database:
            indexed = database.execute(
                """
                SELECT COUNT(*) AS sessions,
                       COALESCE(SUM(s.generation), 0) AS generations,
                       COALESCE(MAX(s.updated_at), '') AS updated_at,
                       COALESCE(SUM(s.turn_count), 0) AS turns
                FROM experiment_correlations AS c
                JOIN sessions AS s ON s.session_id = c.session_id
                WHERE c.experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()
            cost = database.execute(
                """
                SELECT COALESCE(SUM(p.cost_usd), 0) AS cost
                FROM experiment_correlations AS c
                JOIN evidence_payloads AS p ON p.session_id = c.session_id
                WHERE c.experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()
        if not rows and durable_job is None and cursor is None:
            raise ResourceNotFoundError(experiment_id)
        retained_samples: dict[str, ExperimentSampleSummary] = {}
        for row in rows[:limit]:
            run_id = str(row["run_id"])
            if run_id in retained_samples:
                raise ValueError("run identity resolved to multiple sessions")
            retained_samples[run_id] = self._sample(row)
        if durable_job is None:
            samples = tuple(retained_samples.values())
            queue_page: tuple[ExperimentSample, ...] = ()
        else:
            queue_page = durable_page[:limit]
            samples = tuple(
                retained_samples.get(sample.run_id or "")
                or ExperimentSampleSummary(
                    run_id=sample.run_id or sample.id,
                    session_id=None,
                    player_id=durable_job.player_profile,
                    state=sample.state,
                    updated_at=durable_job.updated_at,
                    cost_usd=sample.cost_usd or 0.0,
                    turns=sample.turns or 0,
                )
                for sample in queue_page
            )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=(
                        samples[-1].run_id
                        if durable_job is None
                        else str(queue_page[-1].queue_position)
                    ),
                    secondary=(
                        samples[-1].session_id or ""
                        if durable_job is None
                        else queue_page[-1].id
                    ),
                )
            )
            if (
                (
                    len(rows) > limit
                    if durable_job is None
                    else len(durable_page) > limit
                )
                and samples
            )
            else None
        )
        totals = {
            "samples": 0 if aggregate is None else int(aggregate["samples"]),
            "sessions": 0 if aggregate is None else int(aggregate["sessions"]),
            "cost_usd": 0.0 if cost is None else float(cost["cost"]),
            "turns": 0 if indexed is None else int(indexed["turns"]),
        }
        if durable_job is not None:
            assert store is not None
            totals = store.aggregates(experiment_id)
        version, source_cursor = content_identity(
            "obe1",
            {
                "experiment_id": experiment_id,
                **totals,
                "updated_at": (
                    "" if aggregate is None else str(aggregate["updated_at"])
                ),
                "indexed_sessions": (
                    0 if indexed is None else int(indexed["sessions"])
                ),
                "indexed_generations": (
                    0 if indexed is None else int(indexed["generations"])
                ),
                "indexed_updated_at": (
                    "" if indexed is None else str(indexed["updated_at"])
                ),
                "durable_job": (
                    None
                    if durable_job is None
                    else {
                        "state": durable_job.state,
                        "updated_at": durable_job.updated_at,
                        "definition": durable_job.definition.model_dump(mode="json"),
                        "aggregates": totals,
                    }
                ),
            },
        )
        return ExperimentDetailResponse(
            resource_id=resource_id,
            resource_version=version,
            source_cursor=source_cursor,
            completeness="complete" if durable_job is not None else "partial",
            capture_gaps=(
                ()
                if durable_job is not None
                else (
                    "experiment_definition_unavailable",
                    "experiment_arms_unavailable",
                    "experiment_queue_unavailable",
                )
            ),
            source_refs=(
                "registry.db experiment correlations",
                "observatory index sample summaries",
                *(
                    ()
                    if durable_job is None
                    else ("experiments-v1.sqlite3 durable queue",)
                ),
            ),
            experiment_id=experiment_id,
            continuation_cursor=continuation,
            definition=(
                None
                if durable_job is None
                else ExperimentDefinitionSummary(
                    id=(
                        f"{durable_job.definition.id}:v{durable_job.definition.version}"
                    ),
                    values=durable_job.definition.model_dump(mode="json"),
                )
            ),
            arms=(
                ()
                if durable_job is None
                else tuple(
                    arm.model_dump(mode="json") for arm in durable_job.definition.arms
                )
            ),
            queue=(
                ()
                if durable_job is None
                else tuple(
                    {
                        "id": sample.id,
                        "arm_id": sample.arm_id,
                        "ordinal": sample.ordinal,
                        "position": sample.queue_position,
                        "state": sample.state,
                    }
                    for sample in queue_page
                )
            ),
            aggregates=totals,
            session_links=tuple(
                sample.session_id for sample in samples if sample.session_id
            ),
            samples=samples,
        )

    def _sample(self, row: sqlite3.Row) -> ExperimentSampleSummary:
        session_id = str(row["session_id"])
        checkpoint = self.index.checkpoint(session_id)
        cost_usd = 0.0
        if checkpoint is not None:
            with closing(self._connect()) as database:
                cost_row = database.execute(
                    """
                    SELECT COALESCE(SUM(cost_usd), 0)
                    FROM evidence_payloads
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
            if cost_row is not None:
                cost_usd = float(cost_row[0])
        return ExperimentSampleSummary(
            run_id=str(row["run_id"]),
            session_id=session_id,
            player_id=str(row["player_id"]),
            state=str(row["state"]),
            updated_at=str(row["updated_at"]),
            cost_usd=cost_usd,
            turns=0 if checkpoint is None else checkpoint.turn_count,
        )


def _definition_cursor(definition: ExperimentDefinition) -> str:
    return f"{definition.id}\x1f{definition.version}"


def _definition_cursor_parts(value: str | None) -> tuple[str, int] | None:
    if value is None:
        return None
    definition_id, separator, raw_version = value.rpartition("\x1f")
    if not separator:
        raise ValueError("definition cursor is invalid")
    return definition_id, int(raw_version)
