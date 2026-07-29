from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import httpx
import pytest

from mud_gateway.api import create_app
from mud_gateway.contracts import EventEnvelope
from mud_gateway.journal import Event, Journal
from mud_gateway.stream import (
    EventHub,
    canonical_wire,
    serialize_event,
)


@pytest.fixture()
def journal(tmp_path):
    value = Journal(tmp_path / "journal.db")
    yield value
    value.close()


def test_live_and_replay_use_byte_identical_frames(journal):
    hub = EventHub(journal)
    try:
        subscriber, _ = hub.subscribe("viewer", "s1")
        event = journal.append("s1", "command", {"line": "look"})
        live = subscriber.poll(journal)
        replay = list(hub.replay("s1", after=event.seq - 1))
        assert live == replay
    finally:
        hub.close()


def test_serializer_is_deterministic_and_carries_sequence():
    event = Event(42, "s1", 1.0, 2.0, "command", {"line": "look"})
    first = serialize_event(event)
    assert first == serialize_event(event)
    assert first.startswith("id: 42\n")
    payload = json.loads(first.split("data: ", 1)[1])
    assert EventEnvelope.model_validate(payload).seq == 42


def test_reconnect_replays_exactly_after_last_event_id(journal):
    hub = EventHub(journal)
    try:
        first = journal.append("s1", "wire", {"n": 0})
        journal.append("s1", "wire", {"n": 1})
        journal.append("s1", "wire", {"n": 2})
        _subscriber, missed = hub.subscribe(
            "viewer", "s1", last_event_id=first.seq
        )
        assert len(missed) == 2
        assert f"id: {first.seq + 1}" in missed[0]
    finally:
        hub.close()


def test_slow_subscriber_catches_up_from_the_durable_cursor(journal):
    reader = Journal(journal.path)
    hub = EventHub(reader)
    try:
        subscriber, _ = hub.subscribe("slow", "s1")
        for index in range(700):
            journal.append("s1", "wire", {"n": index})
        frames = subscriber.poll(reader)
        assert len(frames) == 700
        assert subscriber.cursor == journal.last_seq("s1")
    finally:
        hub.close()
        reader.close()


def test_separate_writer_reaches_active_subscriber_without_a_gap(journal):
    reader = Journal(journal.path)
    hub = EventHub(reader)
    try:
        subscriber, missed = hub.subscribe(
            "observatory",
            "s1",
            last_event_id=0,
        )
        assert missed == []
        events = [
            journal.append("s1", "command", {"line": "look"}),
            journal.append("s1", "observation", {"room": "Temple"}),
            journal.append("s1", "future_event", {"kept": True}),
        ]
        live = subscriber.poll(reader)
        replay = list(hub.replay("s1"))
        assert live == replay
        assert [
            json.loads(frame.split("data: ", 1)[1])["seq"]
            for frame in live
        ] == [event.seq for event in events]
    finally:
        hub.close()
        reader.close()


def test_writer_process_reaches_active_subscriber(journal):
    reader = Journal(journal.path)
    hub = EventHub(reader)
    try:
        subscriber, missed = hub.subscribe(
            "observatory",
            "process-session",
            last_event_id=0,
        )
        assert missed == []
        script = "\n".join(
            [
                "import sys",
                "from mud_gateway.journal import Journal",
                "journal = Journal(sys.argv[1])",
                "journal.append(",
                "    'process-session',",
                "    'observation',",
                "    {'room': 'Temple'},",
                "    trace_id='process-trace',",
                ")",
                "journal.close()",
            ]
        )
        subprocess.run(
            [sys.executable, "-c", script, str(journal.path)],
            check=True,
        )
        live = subscriber.poll(reader)
        assert live == list(hub.replay("process-session"))
        assert "process-trace" in live[0]
    finally:
        hub.close()
        reader.close()


def test_canonical_wire_is_exact_with_length_preserving_redaction(journal):
    clear = b"hello"
    journal.append(
        "s1",
        "wire",
        {
            "direction": "in",
            "bytes": len(clear),
            "redacted": False,
            "digest": journal.put_blob(clear),
        },
    )
    journal.append(
        "s1",
        "wire",
        {
            "direction": "out",
            "bytes": 9,
            "redacted": True,
            "digest": None,
        },
    )
    assert canonical_wire(journal, "s1") == clear + b"\x00" * 9


async def test_asgi_live_sse_delivers_an_active_event(journal):
    reader = Journal(journal.path)
    app = create_app(reader)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gateway"
    ) as client:
        request = asyncio.create_task(
            client.get("/sessions/s1/events?limit=1")
        )
        await asyncio.sleep(0.05)
        event = journal.append("s1", "command", {"line": "look"})
        response = await asyncio.wait_for(request, timeout=2)
    assert response.status_code == 200
    assert f"id: {event.seq}" in response.text
    app.state.hub.close()
    reader.close()


async def test_asgi_replay_is_ordered_and_secret_free(journal):
    journal.append("s1", "command", {"line": "look"})
    journal.append(
        "s1",
        "wire",
        {
            "direction": "out",
            "bytes": 12,
            "redacted": True,
            "digest": None,
        },
    )
    app = create_app(journal)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gateway"
    ) as client:
        response = await client.get("/sessions/s1/replay")
        wire = await client.get("/sessions/s1/wire")
    ids = [
        int(line.split(": ", 1)[1])
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert ids == sorted(ids)
    assert b"\x00" * 12 == wire.content
    app.state.hub.close()


async def test_asgi_exposes_canonical_contract_and_capabilities(journal):
    app = create_app(journal)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gateway"
    ) as client:
        contracts = await client.get("/contracts")
        capabilities = await client.get("/capabilities")
    assert contracts.status_code == 200
    assert set(contracts.json()) == {
        "event",
        "capabilities",
        "query",
        "projection",
    }
    assert capabilities.json()["live_cross_process"] is True
    assert capabilities.json()["unknown_events_preserved"] is True
    app.state.hub.close()
