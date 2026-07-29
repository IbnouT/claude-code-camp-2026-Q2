from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mud_gateway.contracts import (
    EventEnvelope,
    EvidenceQuery,
    Gap,
    ProjectionCursor,
    capabilities,
    contract_digest,
    contract_schemas,
)
from mud_gateway.journal import Journal
from mud_gateway.stream import EventHub

FIXTURES = Path(__file__).parent / "fixtures" / "observatory"


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize(
    "name",
    ["complete", "partial", "ambiguous", "unknown"],
)
def test_evidence_fixtures_follow_the_event_contract(name):
    for event in load_fixture(name):
        EventEnvelope.model_validate(event)


def test_event_contract_rejects_accidental_fields():
    event = load_fixture("complete")[0] | {"raw_password": "secret"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(event)


def test_contract_bundle_has_a_stable_manifest():
    schemas = contract_schemas()
    manifest = capabilities()
    assert set(schemas) == {
        "event",
        "capabilities",
        "query",
        "projection",
    }
    assert manifest.contract_digest == contract_digest()
    assert len(manifest.contract_digest) == 16


def test_query_and_projection_contracts_preserve_completeness():
    query = EvidenceQuery(
        session="fixture-ambiguous",
        after=4,
        through=12,
        kinds=("observation", "position"),
    )
    cursor = ProjectionCursor(
        session=query.session,
        through_seq=12,
        event_count=7,
        completeness="gap",
        gaps=(Gap(first=8, last=9),),
        unknown_kinds=("future_evidence",),
        contract_digest=contract_digest(),
    )
    assert query.after == 4
    assert cursor.gaps[0].last == 9


def test_fixture_live_and_replay_prefixes_are_equivalent(tmp_path):
    path = tmp_path / "fixture.db"
    writer = Journal(path)
    reader = Journal(path)
    hub = EventHub(reader)
    try:
        subscriber, missed = hub.subscribe(
            "observatory",
            "fixture-complete",
            last_event_id=0,
        )
        assert missed == []
        for fixture in load_fixture("complete"):
            writer.append(
                fixture["session"],
                fixture["kind"],
                fixture["data"],
                trace_id=fixture["trace_id"],
                at=fixture["at"],
            )
        live = subscriber.poll(reader)
        replay = list(hub.replay("fixture-complete"))
        assert live == replay
    finally:
        hub.close()
        reader.close()
        writer.close()
