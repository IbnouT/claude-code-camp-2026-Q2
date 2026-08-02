"""Read-only repository gates for retained Observatory evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from observatory_v3_backend.errors import (
    MalformedSourceError,
    PathIdentityError,
    UnsupportedSchemaError,
)
from observatory_v3_backend.repositories import (
    AgentRepository,
    ControlRepository,
    EventRepository,
    LifecycleRepository,
    OperatorRepository,
    RegistryDatabase,
    SessionCatalogRepository,
    SessionLookupRepository,
)
from observatory_v3_backend.repositories import session_lookup as lookup_module

from .fixtures import build_retained_fixture


def test_selected_lookup_does_not_open_unrelated_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    original_open = lookup_module.open_readonly_database
    opened_sources: list[Path] = []

    def tracked_open(source: Path) -> sqlite3.Connection:
        opened_sources.append(source)
        return original_open(source)

    monkeypatch.setattr(lookup_module, "open_readonly_database", tracked_open)

    repository = SessionLookupRepository(RegistryDatabase(fixture.config_dir))
    selected = repository.get(fixture.selected_session_id)

    assert selected is not None
    assert selected.session_id == fixture.selected_session_id
    assert opened_sources == [fixture.config_dir / "registry.db"]


def test_catalog_is_registry_only_and_bounded(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path)
    repository = SessionCatalogRepository(RegistryDatabase(fixture.config_dir))

    page = repository.page(limit=5)

    assert len(page) == 5
    assert page[0].session_id == fixture.selected_session_id
    assert page[0].live is True
    with pytest.raises(ValueError, match="between 1 and 500"):
        repository.page(limit=501)


def test_unknown_registry_schema_fails_without_mutation(tmp_path: Path) -> None:
    config_dir = tmp_path / ".boukensha"
    config_dir.mkdir()
    source = config_dir / "registry.db"
    with sqlite3.connect(source) as database:
        database.execute("PRAGMA user_version=99")
        database.execute("CREATE TABLE canary (value TEXT)")
    before = source.read_bytes()

    with pytest.raises(UnsupportedSchemaError):
        RegistryDatabase(config_dir)

    assert source.read_bytes() == before


def test_malformed_registry_schema_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / ".boukensha"
    config_dir.mkdir()
    source = config_dir / "registry.db"
    with sqlite3.connect(source) as database:
        database.execute("PRAGMA user_version=1")
        database.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY)")

    with pytest.raises(MalformedSourceError):
        RegistryDatabase(config_dir)


def test_registry_path_identity_cannot_escape_player_session_root(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    source = fixture.config_dir / "registry.db"
    with sqlite3.connect(source) as database:
        database.execute(
            "UPDATE sessions SET session_dir = ? WHERE session_id = ?",
            (str(tmp_path / "elsewhere"), fixture.selected_session_id),
        )

    repository = SessionLookupRepository(RegistryDatabase(fixture.config_dir))
    with pytest.raises(PathIdentityError):
        repository.get(fixture.selected_session_id)


def test_gateway_events_are_scoped_ordered_and_bounded(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    events = EventRepository(session).page(limit=1)

    assert len(events) == 1
    assert events[0].sequence == 1
    assert events[0].session_id == fixture.selected_gateway_session_id
    assert events[0].payload == {"bytes": 12}


def test_malformed_gateway_payload_is_rejected(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    source = fixture.selected_session_dir / "gateway.db"
    with sqlite3.connect(source) as database:
        database.execute("UPDATE events SET payload = '[]' WHERE seq = 1")
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    with pytest.raises(MalformedSourceError, match="not an object"):
        EventRepository(session).page()


def test_agent_page_preserves_an_incomplete_tail(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    source = fixture.selected_session_dir / "agent.jsonl"
    complete = source.read_bytes()
    source.write_bytes(complete + b'{"phase":"partial"')
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    page = AgentRepository(session).page()

    assert len(page.records) == 2
    assert page.next_offset == len(complete)
    assert page.next_line == 3
    assert page.incomplete_tail is True
    assert [record["line"] for record in page.records] == [1, 2]


def test_malformed_complete_agent_record_is_rejected(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    source = fixture.selected_session_dir / "agent.jsonl"
    source.write_text("not-json\n", encoding="utf-8")
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    with pytest.raises(MalformedSourceError, match="invalid JSONL"):
        AgentRepository(session).page()


def test_operator_messages_include_goal_revision_and_nudge(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    messages = OperatorRepository(session).messages()

    assert [message["action"] for message in messages] == ["revise", "guide"]


def test_unknown_operator_message_version_is_rejected(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    source = fixture.selected_session_dir / "operator-messages.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    value["version"] = 2
    source.write_text(json.dumps(value), encoding="utf-8")
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    with pytest.raises(MalformedSourceError, match="version is unsupported"):
        OperatorRepository(session).messages()


def test_lifecycle_reader_reuses_validated_registry(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    registry = RegistryDatabase(fixture.config_dir)

    lifecycle = LifecycleRepository(registry).page(fixture.selected_session_id)

    assert len(lifecycle) == 1
    assert lifecycle[0].session_id == fixture.selected_session_id
    assert lifecycle[0].detail == {"reason": "fixture"}


def test_control_location_never_reads_token_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    token = fixture.selected_session_dir / "control.token"
    token.write_text("secret-canary", encoding="utf-8")
    session = SessionLookupRepository(RegistryDatabase(fixture.config_dir)).get(
        fixture.selected_session_id
    )
    assert session is not None

    original_read_text = Path.read_text

    def reject_token_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == token:
            raise AssertionError("control token must not be read")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", reject_token_read)
    status = ControlRepository().status(session)

    assert status.state is None
    assert status.available is False
