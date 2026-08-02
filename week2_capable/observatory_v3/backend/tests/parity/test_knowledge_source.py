from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from mud_gateway.knowledge import EvidenceRef, KnowledgeStore

from observatory_v3_backend.app import create_app
from observatory_v3_backend.settings import Settings
from observatory_v3_backend.sources.knowledge import (
    KnowledgeSource,
    KnowledgeSourceError,
)
from observatory_v3_backend.sources.runtime import RuntimeSource


def evidence(session: str, seq: int) -> EvidenceRef:
    return EvidenceRef(
        session_id=session,
        source_seq=seq,
        wire_digest=f"wire-{session}-{seq}",
        parser_version="rules-1",
        method="test-rule",
        observed_at=float(seq),
    )


def store_for(root: Path, player: str) -> KnowledgeStore:
    path = root / "profiles" / player / "knowledge.db"
    path.parent.mkdir(parents=True)
    return KnowledgeStore(path, player_id=player)


def test_player_knowledge_keeps_overlapping_facts_isolated(tmp_path: Path):
    alpha = store_for(tmp_path, "alpha")
    alpha.assert_fact(
        "room:shared",
        "title",
        "Alpha Bakery",
        layer="learned",
        confidence="high",
        evidence=evidence("alpha-session", 4),
    )
    alpha.close()
    beta = store_for(tmp_path, "beta")
    beta.assert_fact(
        "room:shared",
        "title",
        "Beta Bakery",
        layer="learned",
        confidence="high",
        evidence=evidence("beta-session", 8),
    )
    beta.close()

    source = KnowledgeSource(tmp_path)
    alpha_view = source.read("alpha")
    beta_view = source.read("beta")

    assert [item.value for item in alpha_view.assertions] == ["Alpha Bakery"]
    assert [item.value for item in beta_view.assertions] == ["Beta Bakery"]
    assert alpha_view.assertions[0].evidence[0].session_id == "alpha-session"
    assert beta_view.assertions[0].evidence[0].session_id == "beta-session"


def test_knowledge_projection_exposes_support_conflict_snapshot_and_cursor(
    tmp_path: Path,
):
    store = store_for(tmp_path, "alpha")
    first = store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r2",
        layer="learned",
        confidence="medium",
        evidence=evidence("s1", 1),
    )
    store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r2",
        layer="learned",
        confidence="high",
        evidence=evidence("s2", 2),
    )
    conflict = store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r9",
        layer="learned",
        confidence="low",
        evidence=evidence("s2", 3),
    )
    snapshot = store.snapshot("before reset")
    store.reset_learned(reason="baseline reset", snapshot_id=snapshot.snapshot_id)
    store.restore(snapshot.snapshot_id, reason="operator restore")
    cursor = store.last_change_seq()
    store.close()

    result = KnowledgeSource(tmp_path).read("alpha", after=1)

    by_id = {item.assertion_id: item for item in result.assertions}
    assert [item.session_id for item in by_id[first.assertion_id].evidence] == [
        "s1",
        "s2",
    ]
    assert by_id[conflict.assertion_id].conflict_group
    assert result.cdc_cursor == cursor
    assert all(item.change_seq > 1 for item in result.changes)
    assert result.snapshots[0].verified is True
    assert [item.operation for item in result.recoveries] == [
        "reset",
        "restore",
    ]
    assert result.metrics[2].value == 1


def test_missing_store_is_explicit_and_invalid_player_is_rejected(
    tmp_path: Path,
):
    source = KnowledgeSource(tmp_path)

    missing = source.read("alpha")

    assert missing.state == "unavailable"
    assert missing.capture_gaps == ("knowledge store is not available for this player",)
    with pytest.raises(KnowledgeSourceError, match="invalid player id"):
        source.read("../beta")


async def test_player_knowledge_route_is_owned_and_cursor_validated(
    tmp_path: Path,
):
    alpha = store_for(tmp_path, "alpha")
    alpha.assert_fact(
        "player:alpha",
        "state.level",
        4,
        layer="parsed",
        confidence="high",
        evidence=evidence("alpha-session", 3),
    )
    alpha.close()
    app = create_app(Settings(runtime_root=tmp_path, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/players/alpha/knowledge?after=0")
        invalid = await client.get("/api/players/alpha/knowledge?after=-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["player_id"] == "alpha"
    assert payload["source"] == "per-player durable knowledge"
    assert payload["assertions"][0]["value"] == 4
    assert invalid.status_code == 422


async def test_knowledge_ask_reads_only_the_selected_player(
    tmp_path: Path,
):
    for player, value in (
        ("alpha", "Alpha Bakery"),
        ("beta", "Beta Bakery"),
    ):
        store = store_for(tmp_path, player)
        assertion = store.assert_fact(
            "room:shared",
            "title",
            value,
            layer="learned",
            confidence="high",
            evidence=evidence(f"{player}-session", 7),
        )
        assert assertion is not None
        store.close()
    app = create_app(Settings(runtime_root=tmp_path, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "What did this player learn about the Bakery?",
                "scope": {"space": "knowledge", "player_id": "beta"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tier"] == "deterministic"
    assert payload["answer"].startswith("1 matching assertions")
    assert [item["excerpt"] for item in payload["citations"]] == [
        "Beta Bakery",
    ]
    assert all(item["id"].startswith("knowledge:") for item in payload["citations"])


async def test_knowledge_recovery_requires_confirmation_and_selected_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, dict[str, object]]] = []

    def recover(
        _self: RuntimeSource,
        session_id: str,
        **arguments: object,
    ) -> dict[str, object]:
        calls.append((session_id, arguments))
        return {
            "ok": True,
            "action": arguments["action"],
            "player_id": arguments["player_id"],
            "session_id": session_id,
        }

    monkeypatch.setattr(RuntimeSource, "recover_knowledge", recover)
    app = create_app(Settings(runtime_root=tmp_path, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    body = {
        "request_id": "recover-1",
        "action": "restore",
        "session_id": "session-alpha",
        "expected_sequence": 42,
        "confirmed": True,
        "reason": "restore reviewed state",
        "snapshot_id": "snapshot-1",
    }
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        accepted = await client.post(
            "/api/players/alpha/knowledge/recovery",
            json=body,
        )
        rejected = await client.post(
            "/api/players/alpha/knowledge/recovery",
            json={**body, "confirmed": False},
        )

    assert accepted.status_code == 200
    assert calls == [
        (
            "session-alpha",
            {
                "player_id": "alpha",
                "action": "restore",
                "expected_sequence": 42,
                "snapshot_id": "snapshot-1",
                "reason": "restore reviewed state",
            },
        )
    ]
    assert rejected.status_code == 422
