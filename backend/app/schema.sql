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
