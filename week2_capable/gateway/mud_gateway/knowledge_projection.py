"""Project typed gateway observations into one player's durable knowledge."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from .knowledge import EvidenceRef, KnowledgeStore
from .observe import (
    ExitsObservation,
    Observation,
    PlayerStateObservation,
    RoomObservation,
    VitalsObservation,
)
from .position import PositionObservation


class KnowledgeProjector:
    """The gateway-owned writer from immutable observations to learned state."""

    def __init__(self, store: KnowledgeStore, *, player_id: str) -> None:
        self.store = store
        self.player_id = player_id
        self._last_place: str | None = None
        self._place_ids: dict[tuple[str, int], str] = {}

    def ingest(
        self,
        observations: Sequence[Observation],
        position: PositionObservation,
        *,
        attempted_move: str | None = None,
        observed_at: float | None = None,
    ) -> tuple[int, int]:
        """Commit one observation frame and return its CDC range."""
        before = self.store.last_change_seq()
        at = time.time() if observed_at is None else observed_at
        transaction_id = uuid.uuid4().hex

        for observation in observations:
            evidence = EvidenceRef(
                session_id=observation.wire_ref.source,
                source_seq=observation.wire_ref.last_seq,
                wire_digest=observation.wire_ref.digest,
                parser_version=observation.parser_version,
                method=observation.method,
                observed_at=at,
            )
            if isinstance(observation, PlayerStateObservation):
                for name, value in observation.values.items():
                    self.store.assert_fact(
                        f"player:{self.player_id}",
                        f"state.{name}",
                        value,
                        layer="parsed",
                        confidence=observation.confidence.value,
                        evidence=evidence,
                        transaction_id=transaction_id,
                    )
            elif isinstance(observation, VitalsObservation):
                for name, value in {
                    "hit": observation.hit,
                    "mana": observation.mana,
                    "move": observation.move,
                }.items():
                    self.store.assert_fact(
                        f"player:{self.player_id}",
                        f"state.{name}",
                        value,
                        layer="parsed",
                        confidence=observation.confidence.value,
                        evidence=evidence,
                        transaction_id=transaction_id,
                    )
            elif isinstance(observation, ExitsObservation):
                # What the game says lies each way. A name is not proof of
                # identity, so it is kept apart from the ways actually
                # walked: it tells the agent where to aim, and a walk
                # settles what is really there.
                place = self.current_place_id
                if place is not None:
                    for direction, name in (
                        observation.destinations or {}
                    ).items():
                        self.store.assert_fact(
                            place,
                            f"exit_named.{direction}",
                            name,
                            layer="learned",
                            confidence=observation.confidence.value,
                            evidence=evidence,
                            transaction_id=transaction_id,
                        )
            elif isinstance(observation, RoomObservation):
                room_id = self._room_id(position, observation)
                self._learn_room(
                    room_id,
                    observation,
                    evidence,
                    transaction_id=transaction_id,
                )
                if attempted_move and self._last_place and room_id != self._last_place:
                    self.store.assert_fact(
                        self._last_place,
                        f"exit.{attempted_move}",
                        room_id,
                        layer="learned",
                        confidence=position.confidence.value,
                        evidence=evidence,
                        transaction_id=transaction_id,
                    )
                self._last_place = room_id

        position_is_current = any(
            observation.wire_ref == position.wire_ref
            for observation in observations
        )
        if position.wire_ref.source != "none" and position_is_current:
            evidence = EvidenceRef(
                session_id=position.wire_ref.source,
                source_seq=position.wire_ref.last_seq,
                wire_digest=position.wire_ref.digest,
                parser_version=position.parser_version,
                method=position.method,
                observed_at=at,
            )
            self.store.assert_fact(
                f"player:{self.player_id}",
                "position",
                {
                    "place": self._position_place(position),
                    "title": position.title,
                    "confidence": position.confidence.value,
                },
                layer="parsed",
                confidence=position.confidence.value,
                evidence=evidence,
                transaction_id=transaction_id,
            )
        return before + 1, self.store.last_change_seq()

    def _learn_room(
        self,
        room_id: str,
        observation: RoomObservation,
        evidence: EvidenceRef,
        *,
        transaction_id: str,
    ) -> None:
        facts = {
            "title": observation.title,
            "exits": list(observation.exits),
        }
        # An arrival in brief mode carries no room text. Recording that
        # emptiness erases what an earlier look earned, and room identity
        # is keyed partly on the text, so the map comes apart. Saying
        # nothing is not the same as there being nothing.
        if observation.description:
            facts["description"] = list(observation.description)
        for predicate, value in facts.items():
            self.store.assert_fact(
                room_id,
                predicate,
                value,
                layer="learned",
                confidence=observation.confidence.value,
                evidence=evidence,
                transaction_id=transaction_id,
            )
        for kind, values in (
            ("mob", observation.mobs),
            ("object", observation.objects),
        ):
            for index, value in enumerate(values):
                sighting_id = (
                    f"sighting:{evidence.session_id}:{evidence.source_seq}:"
                    f"{kind}:{index}"
                )
                for predicate, item in {
                    "kind": kind,
                    "name": value,
                    "room": room_id,
                }.items():
                    self.store.assert_fact(
                        sighting_id,
                        predicate,
                        item,
                        layer="learned",
                        confidence=observation.confidence.value,
                        evidence=evidence,
                        transaction_id=transaction_id,
                    )

    def _room_id(
        self,
        position: PositionObservation,
        observation: RoomObservation,
    ) -> str:
        if position.place is not None:
            key = (observation.wire_ref.source, position.place)
            return self._place_ids.setdefault(
                key,
                f"place:{observation.wire_ref.source}:"
                f"{observation.wire_ref.first_seq}:{position.place}",
            )
        return (
            f"room-sighting:{observation.wire_ref.source}:"
            f"{observation.wire_ref.last_seq}:{observation.wire_ref.digest}"
        )

    @property
    def current_place_id(self) -> str | None:
        """The stable store identity of the last observed place, if any."""
        return self._last_place

    def _position_place(self, position: PositionObservation) -> str | None:
        if position.place is None:
            return None
        return self._place_ids.get(
            (position.wire_ref.source, position.place)
        )
