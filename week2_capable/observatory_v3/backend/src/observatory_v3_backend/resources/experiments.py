"""Bounded experiment catalog and sample resources."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from ..database import open_readonly_database
from .base import ResourceBase, ResourceNotFoundError, validate_limit
from .bounds import content_identity
from .contracts import (
    ExperimentCatalogPage,
    ExperimentDetailResponse,
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
        clauses = ["experiment_id IS NOT NULL", "run_id IS NOT NULL"]
        arguments: list[object] = []
        if after is not None:
            clauses.append("experiment_id > ?")
            arguments.append(after.primary)
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
        experiments = tuple(
            ExperimentSummary(
                experiment_id=str(row["experiment_id"]),
                sample_count=int(row["sample_count"]),
                session_count=int(row["session_count"]),
                latest_session_at=str(row["latest_session_at"]),
            )
            for row in rows[:limit]
        )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=experiments[-1].experiment_id,
                    secondary="",
                )
            )
            if len(rows) > limit and experiments
            else None
        )
        identity = {
            "experiments": 0 if aggregate is None else int(aggregate["experiments"]),
            "samples": 0 if aggregate is None else int(aggregate["samples"]),
            "updated_at": "" if aggregate is None else str(aggregate["updated_at"]),
        }
        version, source_cursor = content_identity("obe1", identity)
        return ExperimentCatalogPage(
            resource_id=resource_id,
            resource_version=version,
            source_cursor=source_cursor,
            completeness="partial",
            capture_gaps=(
                "experiment_definitions_unavailable",
                "experiment_jobs_unavailable",
            ),
            source_refs=("registry.db experiment correlations",),
            continuation_cursor=continuation,
            experiments=experiments,
            definitions=(),
            jobs=(),
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
        clauses = ["experiment_id = ?", "run_id IS NOT NULL"]
        arguments: list[object] = [experiment_id]
        if after is not None:
            clauses.append("(run_id, session_id) > (?, ?)")
            arguments.extend((after.primary, after.secondary))
        arguments.append(limit + 1)
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
        if not rows and cursor is None:
            raise ResourceNotFoundError(experiment_id)
        samples = tuple(self._sample(row) for row in rows[:limit])
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=samples[-1].run_id,
                    secondary=samples[-1].session_id,
                )
            )
            if len(rows) > limit and samples
            else None
        )
        totals = {
            "samples": 0 if aggregate is None else int(aggregate["samples"]),
            "sessions": 0 if aggregate is None else int(aggregate["sessions"]),
            "cost_usd": 0.0 if cost is None else float(cost["cost"]),
            "turns": 0 if indexed is None else int(indexed["turns"]),
        }
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
            },
        )
        return ExperimentDetailResponse(
            resource_id=resource_id,
            resource_version=version,
            source_cursor=source_cursor,
            completeness="partial",
            capture_gaps=(
                "experiment_definition_unavailable",
                "experiment_arms_unavailable",
                "experiment_queue_unavailable",
            ),
            source_refs=(
                "registry.db experiment correlations",
                "observatory index sample summaries",
            ),
            experiment_id=experiment_id,
            continuation_cursor=continuation,
            definition=None,
            arms=(),
            queue=(),
            aggregates=totals,
            session_links=tuple(sample.session_id for sample in samples),
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
