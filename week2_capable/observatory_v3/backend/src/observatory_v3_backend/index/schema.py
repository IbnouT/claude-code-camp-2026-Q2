"""Owner-controlled schema for disposable derived Observatory data."""

from __future__ import annotations

INDEX_SCHEMA_VERSION = 4
PROJECTOR_VERSION = 1

MIGRATIONS = {
    1: """
        ALTER TABLE source_watermarks
        ADD COLUMN gateway_source_id TEXT NOT NULL DEFAULT 'unknown';
        ALTER TABLE source_watermarks
        ADD COLUMN knowledge_revision TEXT;
        ALTER TABLE source_watermarks
        ADD COLUMN operator_message_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE source_watermarks
        ADD COLUMN operator_history_digest TEXT NOT NULL
            DEFAULT '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945';
        ALTER TABLE source_watermarks
        ADD COLUMN operator_state TEXT NOT NULL DEFAULT '[]';
    """,
    2: """
        CREATE TABLE evidence_payloads (
            entity_id TEXT PRIMARY KEY
                REFERENCES entities(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            evidence_kind TEXT NOT NULL,
            trace_id TEXT,
            payload TEXT NOT NULL,
            integrity_digest TEXT NOT NULL,
            duration_ms REAL,
            tokens INTEGER,
            cost_usd REAL
        );
        CREATE INDEX evidence_session_kind
        ON evidence_payloads(
            session_id,
            evidence_kind,
            entity_id,
            trace_id
        );
        CREATE INDEX evidence_session_cost
        ON evidence_payloads(session_id, cost_usd, entity_id);

        UPDATE source_watermarks
        SET gateway_source_id = 'unknown';
    """,
    3: """
        CREATE TABLE IF NOT EXISTS materialization_faults (
            session_id TEXT PRIMARY KEY,
            detail TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    character TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ended_at TEXT,
    capture_status TEXT NOT NULL,
    latest_goal_id TEXT,
    latest_goal TEXT,
    goal_count INTEGER NOT NULL CHECK (goal_count >= 0),
    nudge_count INTEGER NOT NULL CHECK (nudge_count >= 0),
    turn_count INTEGER NOT NULL CHECK (turn_count >= 0),
    iteration_count INTEGER NOT NULL CHECK (iteration_count >= 0),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    projector_version INTEGER NOT NULL,
    capture_gaps TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_catalog
ON sessions(
    updated_at DESC,
    session_id DESC,
    player_id,
    character,
    state,
    created_at,
    ended_at,
    capture_status,
    latest_goal,
    goal_count,
    nudge_count,
    turn_count,
    iteration_count,
    generation
);

CREATE INDEX IF NOT EXISTS sessions_player_catalog
ON sessions(
    player_id,
    updated_at DESC,
    session_id DESC,
    character,
    state,
    created_at,
    ended_at,
    capture_status,
    latest_goal,
    goal_count,
    nudge_count,
    turn_count,
    iteration_count,
    generation
);

CREATE TABLE IF NOT EXISTS source_watermarks (
    session_id TEXT PRIMARY KEY
        REFERENCES sessions(session_id) ON DELETE CASCADE,
    registry_updated_at TEXT NOT NULL,
    lifecycle_sequence INTEGER NOT NULL CHECK (lifecycle_sequence >= 0),
    gateway_session_id TEXT NOT NULL,
    gateway_source_id TEXT NOT NULL,
    gateway_sequence INTEGER NOT NULL CHECK (gateway_sequence >= 0),
    agent_source_id TEXT NOT NULL,
    agent_offset INTEGER NOT NULL CHECK (agent_offset >= 0),
    agent_next_line INTEGER NOT NULL CHECK (agent_next_line >= 1),
    operator_source_id TEXT NOT NULL,
    operator_revision TEXT NOT NULL,
    operator_message_count INTEGER NOT NULL
        CHECK (operator_message_count >= 0),
    operator_history_digest TEXT NOT NULL,
    operator_state TEXT NOT NULL,
    experiment_revision TEXT,
    knowledge_revision TEXT
);

CREATE TABLE IF NOT EXISTS materialization_faults (
    session_id TEXT PRIMARY KEY,
    detail TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES sessions(session_id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_anchor TEXT NOT NULL,
    parent_id TEXT,
    goal_id TEXT,
    turn_id TEXT,
    iteration_id TEXT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    occurred_at TEXT NOT NULL,
    title TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    UNIQUE(session_id, kind, source_anchor),
    FOREIGN KEY(parent_id) REFERENCES entities(id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(goal_id) REFERENCES entities(id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(turn_id) REFERENCES entities(id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(iteration_id) REFERENCES entities(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS entities_session_order
ON entities(session_id, ordinal, id);

CREATE INDEX IF NOT EXISTS entities_goal_order
ON entities(session_id, goal_id, ordinal, id);

CREATE INDEX IF NOT EXISTS entities_trace_anchor
ON entities(session_id, kind, source_anchor);

CREATE TABLE IF NOT EXISTS experiment_correlations (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE
        REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE(experiment_id, run_id)
);

CREATE TABLE IF NOT EXISTS search_documents (
    entity_id TEXT PRIMARY KEY
        REFERENCES entities(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_payloads (
    entity_id TEXT PRIMARY KEY
        REFERENCES entities(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    trace_id TEXT,
    payload TEXT NOT NULL,
    integrity_digest TEXT NOT NULL,
    duration_ms REAL,
    tokens INTEGER,
    cost_usd REAL
);

CREATE INDEX IF NOT EXISTS evidence_session_cost
ON evidence_payloads(session_id, cost_usd, entity_id);

CREATE INDEX IF NOT EXISTS evidence_session_kind
ON evidence_payloads(
    session_id,
    evidence_kind,
    entity_id,
    trace_id
);

CREATE INDEX IF NOT EXISTS search_scope
ON search_documents(session_id, player_id, kind, occurred_at, entity_id);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    title,
    body,
    content='search_documents',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS search_documents_insert
AFTER INSERT ON search_documents BEGIN
    INSERT INTO search_fts(rowid, title, body)
    VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS search_documents_delete
AFTER DELETE ON search_documents BEGIN
    INSERT INTO search_fts(search_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS search_documents_update
AFTER UPDATE ON search_documents BEGIN
    INSERT INTO search_fts(search_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO search_fts(rowid, title, body)
    VALUES (new.rowid, new.title, new.body);
END;
"""
