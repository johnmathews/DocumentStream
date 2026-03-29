-- DocumentStream database schema
-- Run this against PostgreSQL before starting the store worker.
--
-- Requires: PostgreSQL 16+ with pgvector extension
-- The pgvector/pgvector:pg16 Docker image has the extension pre-installed.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    -- Primary key
    doc_id          TEXT PRIMARY KEY,

    -- Document metadata
    filename        TEXT NOT NULL,
    text            TEXT NOT NULL,
    page_count      INTEGER NOT NULL,
    word_count      INTEGER NOT NULL,

    -- Rule-based classification
    classification  TEXT NOT NULL,           -- Public / Confidential / Secret
    confidence      REAL NOT NULL,
    matched_keywords JSONB NOT NULL DEFAULT '{}',
    scores          JSONB NOT NULL DEFAULT '{}',

    -- Semantic classification
    semantic_privacy            TEXT NOT NULL,
    semantic_privacy_confidence REAL NOT NULL,
    environmental_impact        TEXT NOT NULL,       -- None / Low / Medium / High
    environmental_confidence    REAL NOT NULL,
    industries                  JSONB NOT NULL DEFAULT '[]',

    -- Embedding for pgvector semantic search (384 dims = all-MiniLM-L6-v2)
    embedding       vector(384),

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for filtering by classification level
CREATE INDEX IF NOT EXISTS idx_documents_classification ON documents (classification);

-- Index for filtering by environmental impact
CREATE INDEX IF NOT EXISTS idx_documents_environmental ON documents (environmental_impact);

-- HNSW index for approximate nearest neighbor search on embeddings
-- Use cosine distance (<=>) since embeddings are normalized
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
