-- ModelScopeX schema v1.
-- Claims are append-only: a changed value is a new row; triggers block UPDATE and DELETE.

CREATE TABLE models (
    id              TEXT PRIMARY KEY,          -- Hugging Face repo id, lowercased
    repo_id         TEXT NOT NULL,             -- original casing
    slug            TEXT NOT NULL UNIQUE,
    author          TEXT NOT NULL,
    category        TEXT NOT NULL,             -- HF pipeline tag the model was discovered under
    first_seen_at   TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    downloads       INTEGER,                   -- latest value only, never a claim
    likes           INTEGER                    -- latest value only, never a claim
);

CREATE TABLE sources (
    id           INTEGER PRIMARY KEY,
    url          TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL CHECK (kind IN
                   ('hf_api', 'hf_model_card', 'github', 'paper', 'vendor_blog', 'own_eval')),
    retrieved_at TEXT NOT NULL
);

CREATE TABLE claims (
    id          INTEGER PRIMARY KEY,
    model_id    TEXT NOT NULL REFERENCES models(id),
    field       TEXT NOT NULL,
    value       TEXT NOT NULL,                 -- JSON-encoded; null when status is 'unknown'
    source_id   INTEGER NOT NULL REFERENCES sources(id),
    status      TEXT NOT NULL CHECK (status IN
                  ('publisher_declared', 'independently_measured', 'estimated', 'unknown')),
    observed_at TEXT NOT NULL
);

CREATE INDEX claims_model_field ON claims (model_id, field, id);

CREATE TRIGGER claims_no_update BEFORE UPDATE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims are append-only');
END;

CREATE TRIGGER claims_no_delete BEFORE DELETE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims are append-only');
END;

CREATE TABLE runs (
    id          INTEGER PRIMARY KEY,
    command     TEXT NOT NULL,
    args        TEXT NOT NULL,                 -- JSON
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER,
    message     TEXT                           -- JSON summary
);
