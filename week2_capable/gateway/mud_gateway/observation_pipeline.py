"""Persist parsed state while keeping every result linked to source bytes."""

from __future__ import annotations

from dataclasses import dataclass

from .journal import Journal
from .knowledge_projection import KnowledgeProjector
from .observe import (
    PARSER_VERSION,
    Coverage,
    Observation,
    RoomObservation,
    VitalsObservation,
    WireReference,
    normalized_text,
    parse,
)
from .position import PositionObservation, PositionTracker


@dataclass(frozen=True)
class ObservationSnapshot:
    room: RoomObservation | None
    vitals: VitalsObservation | None
    position: PositionObservation
    miss_rate: float


class ObservationPipeline:
    """Parse, journal, and retain only the latest derived state."""

    def __init__(
        self,
        journal: Journal,
        session: str,
        *,
        knowledge: KnowledgeProjector | None = None,
    ) -> None:
        self.journal = journal
        self.session = session
        self.knowledge = knowledge
        self.coverage = Coverage()
        self.tracker = PositionTracker()
        self.room: RoomObservation | None = None
        self.vitals: VitalsObservation | None = None
        self.posture: str | None = None

    def ingest(
        self,
        raw: bytes,
        wire_ref: WireReference,
        *,
        attempted_move: str | None = None,
        trace_id: str | None = None,
    ) -> tuple[tuple[Observation, ...], PositionObservation]:
        if attempted_move:
            self.tracker.moving(attempted_move)
        self.journal.append(
            self.session,
            "parser_input",
            {
                "text": normalized_text(raw),
                "bytes": len(raw),
                "encoding": "latin-1",
                "transformations": (
                    "normalize_newlines",
                    "remove_ansi_sgr",
                    "remove_blank_lines",
                    "trim_lines",
                ),
                "wire_ref": {
                    "source": wire_ref.source,
                    "first_seq": wire_ref.first_seq,
                    "last_seq": wire_ref.last_seq,
                    "digest": wire_ref.digest,
                },
                "parser_version": PARSER_VERSION,
            },
            trace_id=trace_id,
        )
        observations = parse(raw, wire_ref)
        frame_coverage = Coverage()
        frame_coverage.add(observations)
        self.coverage.add(observations)

        for observation in observations:
            if isinstance(observation, RoomObservation):
                self.room = observation
            elif isinstance(observation, VitalsObservation):
                self.vitals = observation
            else:
                posture = getattr(observation, "values", {}).get("posture")
                if isinstance(posture, str):
                    self.posture = posture
            self.journal.append(
                self.session,
                "unparsed" if observation.kind == "unparsed" else "observation",
                observation.payload(),
                trace_id=trace_id,
            )

        before = self.tracker.position
        position = self.tracker.observe(observations)
        if position != before:
            self.journal.append(
                self.session,
                "position",
                position.payload(),
                trace_id=trace_id,
            )
        if self.knowledge is not None:
            first_change, last_change = self.knowledge.ingest(
                observations,
                position,
                attempted_move=attempted_move,
            )
            if last_change >= first_change:
                self.journal.append(
                    self.session,
                    "knowledge_change",
                    {
                        "player_id": self.knowledge.player_id,
                        "first_change_seq": first_change,
                        "last_change_seq": last_change,
                    },
                    trace_id=trace_id,
                )
        self.journal.append(
            self.session,
            "parse_metric",
            {
                "parser_version": observations[0].parser_version if observations else PARSER_VERSION,
                "wire_ref": {
                    "source": wire_ref.source,
                    "first_seq": wire_ref.first_seq,
                    "last_seq": wire_ref.last_seq,
                    "digest": wire_ref.digest,
                },
                "lines": frame_coverage.lines,
                "typed": frame_coverage.typed,
                "miss_rate": frame_coverage.miss_rate,
                "cumulative_miss_rate": self.coverage.miss_rate,
            },
            trace_id=trace_id,
        )
        return tuple(observations), position

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            room=self.room,
            vitals=self.vitals,
            position=self.tracker.position,
            miss_rate=self.coverage.miss_rate,
        )
