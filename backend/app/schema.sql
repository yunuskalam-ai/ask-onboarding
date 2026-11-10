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

-- Notifications: one row per event, and one recipient row per person it
-- concerns, so each person has their own read/unread state. Recipients are
-- decided when the event happens (see app/notifications.py).
CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind        TEXT NOT NULL CHECK (kind IN ('ticket.opened', 'ticket.updated', 'system.alert')),
    severity    TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'error')),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    link        TEXT,                           -- an in-app path, e.g. /tickets#ticket-7
    ticket_id   BIGINT REFERENCES tickets(id) ON DELETE CASCADE,
    dedupe_key  TEXT                            -- system alerts: at most one per key per 10 minutes
);
CREATE INDEX IF NOT EXISTS notifications_dedupe_idx ON notifications (dedupe_key, at DESC) WHERE dedupe_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS notification_recipients (
    notification_id  BIGINT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at          TIMESTAMPTZ,              -- NULL = unread
    PRIMARY KEY (notification_id, user_id)
);
-- "My unread notifications" is the query the header bell runs every 30 seconds.
CREATE INDEX IF NOT EXISTS notification_recipients_unread_idx
    ON notification_recipients (user_id) WHERE read_at IS NULL;

-- People management: departments, reporting lines and active/inactive.
CREATE TABLE IF NOT EXISTS departments (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS departments_name_idx ON departments (lower(name));

-- Inactive people can't sign in and receive nothing; their history stays.
ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE users ADD COLUMN IF NOT EXISTS department_id BIGINT REFERENCES departments(id) ON DELETE SET NULL;
-- Who this person reports to. A manager's team is everyone below them in
-- this tree (direct reports, their reports, and so on). Loops are refused
-- by the API; a database check stops the simplest one, reporting to yourself.
ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_not_own_manager;
ALTER TABLE users ADD CONSTRAINT users_not_own_manager CHECK (manager_id IS NULL OR manager_id <> id);
CREATE INDEX IF NOT EXISTS users_manager_idx ON users (manager_id);

-- Alert details: an ongoing problem is one alert that counts its repeats.
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS occurrences INT NOT NULL DEFAULT 1;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
UPDATE notifications SET last_seen_at = at WHERE last_seen_at IS NULL;
-- System alerts open their detail page (older ones pointed at the overview).
UPDATE notifications SET link = '/alerts/' || id WHERE kind = 'system.alert' AND link = '/overview';

-- A readable title for each document ("Paid Time Off and Leave Policy"),
-- set when it is processed; older documents get it on the next start.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS title TEXT;
