"""SQLite schema for per-player knowledge."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    fact_id               TEXT PRIMARY KEY,
    subject               TEXT NOT NULL,
    predicate             TEXT NOT NULL,
    layer                 TEXT NOT NULL,
    current_assertion_id  TEXT,
    created_at            REAL NOT NULL,
    UNIQUE(subject, predicate, layer)
);
CREATE TABLE IF NOT EXISTS assertions (
    assertion_id   TEXT PRIMARY KEY,
    fact_id        TEXT NOT NULL REFERENCES facts(fact_id),
    value_json     TEXT NOT NULL CHECK (json_valid(value_json)),
    value_digest   TEXT NOT NULL,
    status         TEXT NOT NULL,
    confidence     TEXT NOT NULL,
    method         TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    source_seq     INTEGER NOT NULL,
    wire_digest    TEXT NOT NULL,
    observed_at    REAL NOT NULL,
    supersedes     TEXT,
    conflict_group TEXT,
    transaction_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assertions_by_fact
    ON assertions(fact_id, observed_at, assertion_id);
CREATE TABLE IF NOT EXISTS evidence_refs (
    evidence_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    assertion_id   TEXT NOT NULL REFERENCES assertions(assertion_id),
    session_id     TEXT NOT NULL,
    source_seq     INTEGER NOT NULL,
    wire_digest    TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    method         TEXT NOT NULL,
    observed_at    REAL NOT NULL,
    UNIQUE(assertion_id, session_id, source_seq, wire_digest)
);
CREATE TABLE IF NOT EXISTS resolutions (
    resolution_id  TEXT PRIMARY KEY,
    fact_id        TEXT NOT NULL REFERENCES facts(fact_id),
    assertion_id   TEXT NOT NULL REFERENCES assertions(assertion_id),
    reason         TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    at             REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
    change_seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    operation      TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    before_digest  TEXT,
    after_digest   TEXT,
    session_id     TEXT,
    source_seq     INTEGER,
    at             REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS changes_by_transaction
    ON changes(transaction_id, change_seq);
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    cdc_high_water INTEGER NOT NULL,
    reason         TEXT NOT NULL,
    digest         TEXT NOT NULL,
    generation     INTEGER NOT NULL,
    at             REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot_facts (
    snapshot_id  TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    assertion_id TEXT NOT NULL REFERENCES assertions(assertion_id),
    PRIMARY KEY(snapshot_id, assertion_id)
);
CREATE TABLE IF NOT EXISTS rebuilds (
    rebuild_id      TEXT PRIMARY KEY,
    parser_version  TEXT NOT NULL,
    source_first_at REAL,
    source_last_at  REAL,
    assertions      INTEGER NOT NULL,
    transaction_id  TEXT NOT NULL,
    at              REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS restores (
    restore_id     TEXT PRIMARY KEY,
    snapshot_id    TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    reason         TEXT NOT NULL,
    assertions     INTEGER NOT NULL,
    transaction_id TEXT NOT NULL,
    at             REAL NOT NULL
);
"""
