"""Persist parsed state while keeping every result linked to source bytes."""

from __future__ import annotations

from dataclasses import dataclass

from .journal import Journal
from .observe import (
    PARSER_VERSION,
    Coverage,
    Observation,
    RoomObservation,
    VitalsObservation,
    WireReference,
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

    def __init__(self, journal: Journal, session: str) -> None:
        self.journal = journal
        self.session = session
        self.coverage = Coverage()
        self.tracker = PositionTracker()
        self.room: RoomObservation | None = None
        self.vitals: VitalsObservation | None = None

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
        observations = parse(raw, wire_ref)
        frame_coverage = Coverage()
        frame_coverage.add(observations)
        self.coverage.add(observations)

        for observation in observations:
            if isinstance(observation, RoomObservation):
                self.room = observation
            elif isinstance(observation, VitalsObservation):
                self.vitals = observation
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

