"""Ordered live subscription and replay through one SSE serializer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Iterator

from .contracts import EventEnvelope
from .journal import Event, Journal

READ_BATCH = 512


def serialize_event(event: Event) -> str:
    envelope = EventEnvelope(
        seq=event.seq,
        session=event.session,
        at=event.at,
        kind=event.kind,
        trace_id=event.trace_id,
        data=event.payload,
    )
    payload = json.dumps(
        envelope.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {event.seq}\nevent: {event.kind}\ndata: {payload}\n\n"


@dataclass
class Subscriber:
    name: str
    session: str
    cursor: int
    kinds: frozenset[str] | None = None

    def wants(self, event: Event) -> bool:
        return event.session == self.session and (
            self.kinds is None or event.kind in self.kinds
        )

    def poll(
        self,
        journal: Journal,
        *,
        limit: int | None = None,
    ) -> list[str]:
        """Read committed events after this subscriber's durable cursor."""

        frames: list[str] = []
        while limit is None or len(frames) < limit:
            events = journal.since(
                self.session,
                after=self.cursor,
                limit=READ_BATCH,
            )
            if not events:
                break
            for event in events:
                self.cursor = event.seq
                if self.wants(event):
                    frames.append(serialize_event(event))
                    if limit is not None and len(frames) >= limit:
                        break
            if len(events) < READ_BATCH:
                break
        return frames


class EventHub:
    """Serve committed events through durable, cross-process cursors."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.subscribers: list[Subscriber] = []

    def subscribe(
        self,
        name: str,
        session: str,
        *,
        kinds: Iterable[str] | None = None,
        last_event_id: int | None = None,
    ) -> tuple[Subscriber, list[str]]:
        cursor = (
            self.journal.last_seq(session)
            if last_event_id is None
            else last_event_id
        )
        subscriber = Subscriber(
            name=name,
            session=session,
            cursor=cursor,
            kinds=None if kinds is None else frozenset(kinds),
        )
        self.subscribers.append(subscriber)
        missed = (
            []
            if last_event_id is None
            else subscriber.poll(self.journal)
        )
        return subscriber, missed

    def unsubscribe(self, subscriber: Subscriber) -> None:
        if subscriber in self.subscribers:
            self.subscribers.remove(subscriber)

    def replay(
        self,
        session: str,
        *,
        after: int = 0,
        kinds: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> Iterator[str]:
        wanted = None if kinds is None else frozenset(kinds)
        for event in self.journal.since(session, after=after, limit=limit):
            if wanted is None or event.kind in wanted:
                yield serialize_event(event)

    def close(self) -> None:
        self.subscribers.clear()


def canonical_wire(journal: Journal, session: str) -> bytes:
    """Rebuild the captured stream, using zero bytes where capture redacted."""

    rebuilt = bytearray()
    for event in journal.since(session, kind="wire"):
        count = int(event.payload["bytes"])
        if event.payload.get("redacted"):
            rebuilt.extend(b"\x00" * count)
            continue
        digest = event.payload.get("digest")
        body = journal.get_blob(digest) if digest else b""
        if body is None or len(body) != count:
            raise ValueError(f"wire event {event.seq} has no byte-exact body")
        rebuilt.extend(body)
    return bytes(rebuilt)
