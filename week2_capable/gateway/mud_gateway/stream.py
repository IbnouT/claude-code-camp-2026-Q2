"""Ordered live subscription and replay through one SSE serializer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .journal import Event, Journal

BACKLOG_LIMIT = 512


def serialize_event(event: Event) -> str:
    payload = json.dumps(
        {
            "seq": event.seq,
            "session": event.session,
            "at": event.at,
            "kind": event.kind,
            "trace_id": event.trace_id,
            "data": event.payload,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {event.seq}\nevent: {event.kind}\ndata: {payload}\n\n"


@dataclass
class Subscriber:
    name: str
    session: str
    kinds: frozenset[str] | None = None
    backlog: list[Event] = field(default_factory=list)
    dropped: bool = False

    def wants(self, event: Event) -> bool:
        return event.session == self.session and (
            self.kinds is None or event.kind in self.kinds
        )

    def offer(self, event: Event) -> bool:
        if self.dropped:
            return False
        if len(self.backlog) >= BACKLOG_LIMIT:
            self.dropped = True
            self.backlog.clear()
            return False
        self.backlog.append(event)
        return True

    def drain(self) -> Iterator[str]:
        pending, self.backlog = self.backlog, []
        for event in pending:
            yield serialize_event(event)


class EventHub:
    """Fan committed events out without ever blocking the journal writer."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.subscribers: list[Subscriber] = []
        self._recording_drop = False
        self._cancel = journal.subscribe(self._publish)

    def subscribe(
        self,
        name: str,
        session: str,
        *,
        kinds: Iterable[str] | None = None,
        last_event_id: int | None = None,
    ) -> tuple[Subscriber, list[str]]:
        subscriber = Subscriber(
            name=name,
            session=session,
            kinds=None if kinds is None else frozenset(kinds),
        )
        self.subscribers.append(subscriber)
        missed = []
        if last_event_id is not None:
            missed = [
                serialize_event(event)
                for event in self.journal.since(session, after=last_event_id)
                if subscriber.wants(event)
            ]
        return subscriber, missed

    def unsubscribe(self, subscriber: Subscriber) -> None:
        if subscriber in self.subscribers:
            self.subscribers.remove(subscriber)

    def _publish(self, event: Event) -> None:
        dropped: list[Subscriber] = []
        for subscriber in list(self.subscribers):
            if subscriber.wants(event) and not subscriber.offer(event):
                dropped.append(subscriber)
                self.unsubscribe(subscriber)
        if not dropped or self._recording_drop:
            return
        self._recording_drop = True
        try:
            for subscriber in dropped:
                self.journal.append(
                    event.session,
                    "subscriber_dropped",
                    {
                        "subscriber": subscriber.name,
                        "at_seq": event.seq,
                        "reason": "backlog_limit",
                    },
                )
        finally:
            self._recording_drop = False

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
        self._cancel()
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

