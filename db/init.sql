-- Runs once, on the first start of an empty database volume.
-- Tables are created by the API in Phase 1; here we only enable pgvector.
CREATE EXTENSION IF NOT EXISTS vector;
