-- Applied on every API start. Every statement is safe to run again.
-- The vector size (384) must match EMBEDDING_DIM.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    filename      TEXT NOT NULL UNIQUE,          -- re-uploading the same name replaces the document
    content_hash  TEXT NOT NULL,                 -- sha256 of the file bytes
    file_type     TEXT NOT NULL CHECK (file_type IN ('pdf', 'md', 'txt')),
    status        TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    error         TEXT,
    original      BYTEA NOT NULL,                -- the uploaded file, served for citations
    pages         JSONB,                         -- [{"number": 1 or null, "text": "..."}], for highlighting
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    page         INT,                            -- PDF page number, NULL for MD/TXT
    start_char   INT NOT NULL,                   -- offsets into that page's text
    end_char     INT NOT NULL,
    text         TEXT NOT NULL,
    embedding    vector(384) NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (document_id, chunk_index)
);

-- Approximate nearest-neighbour index for cosine distance (vector search).
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
-- Full-text index for the keyword half of hybrid search (Phase 8).
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);

-- Help-desk tickets for questions the documents could not answer.
CREATE TABLE IF NOT EXISTS tickets (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    question    TEXT NOT NULL,                  -- what the employee asked, word for word
    summary     TEXT NOT NULL DEFAULT '',       -- drafted by the model, edited by the employee
    user_name   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',   -- see tickets_status_check below
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- People who can sign in, and what they may do. Demo accounts have no
-- password for now: the sign-in page lists them (see app/auth.py).
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,           -- stored in lowercase
    name        TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('employee', 'manager', 'admin')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Signed-in browsers. The cookie holds a random token; only its SHA-256 is
-- stored, so reading this table doesn't let anyone take over a session.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

-- Who did what, for the admin overview: sign-ins, uploads, role changes, tickets.
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,                  -- e.g. 'sign_in', 'document.upload', 'user.role'
    details     JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_log_at_idx ON audit_log (at DESC);

-- Tickets belong to the person who opened them (older tickets have none).
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS created_by BIGINT REFERENCES users(id) ON DELETE SET NULL;

-- Ticket workflow: open -> in_progress -> resolved -> closed (and back, to
-- reopen). Phase 1 had only open/closed; dropping and re-adding the check
-- upgrades an existing database, and both statuses are still valid.
ALTER TABLE tickets DROP CONSTRAINT IF EXISTS tickets_status_check;
ALTER TABLE tickets ADD CONSTRAINT tickets_status_check
    CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'));
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Every status change: who, when, from what to what, and an optional note.
-- The note is how the help desk answers; the employee sees it on their ticket.
CREATE TABLE IF NOT EXISTS ticket_events (
    id           BIGSERIAL PRIMARY KEY,
    ticket_id    BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    user_name    TEXT NOT NULL,                  -- kept even if the user is deleted
    from_status  TEXT NOT NULL,
    to_status    TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ticket_events_ticket_idx ON ticket_events (ticket_id, at);

-- Every question asked in the chat, for the admin overview: how often the
-- documents answer, what they don't cover, and how fast answers start.
-- Admins can read these; see GUIDE.md on privacy.
CREATE TABLE IF NOT EXISTS questions (
    id              BIGSERIAL PRIMARY KEY,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id         BIGINT REFERENCES users(id) ON DELETE SET NULL,
    user_name       TEXT NOT NULL,
    question        TEXT NOT NULL,
    -- answered | low_score (off-topic, the model was not called) | not_in_sources
    -- (the model said the documents don't cover it) | refused (safety) |
    -- error (the model failed) | stopped (the browser left mid-answer)
    outcome         TEXT NOT NULL CHECK (outcome IN
                        ('answered', 'low_score', 'not_in_sources', 'refused', 'error', 'stopped')),
    best_score      REAL,                       -- best retrieval similarity
    sources         TEXT[] NOT NULL DEFAULT '{}',  -- files the answer cited
    first_token_ms  INT,                        -- NULL when no text was streamed
    total_ms        INT NOT NULL
);
CREATE INDEX IF NOT EXISTS questions_at_idx ON questions (at DESC);
