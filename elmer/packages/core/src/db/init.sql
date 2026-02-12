-- ============================================================
-- Elmer — Database Schema Initialization
-- Requires: PostgreSQL 14+ with pgvector extension
-- ============================================================

-- Enable pgvector for embedding storage and similarity search.
CREATE EXTENSION IF NOT EXISTS vector;

-- All Elmer tables live under their own schema.
CREATE SCHEMA IF NOT EXISTS elmer;

-- -----------------------------------------------------------
-- Node registry — tracks all machines in the Elmer network
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS elmer.nodes (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR NOT NULL UNIQUE,
    node_type       VARCHAR NOT NULL DEFAULT 'generic',
    host            VARCHAR NOT NULL DEFAULT '',
    port            INTEGER NOT NULL DEFAULT 0,
    last_seen       TIMESTAMPTZ,
    status          VARCHAR NOT NULL DEFAULT 'unknown',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Event log — append-only stream of system events
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS elmer.events (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          VARCHAR NOT NULL,
    event_type      VARCHAR NOT NULL,
    data            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_source_type_ts
    ON elmer.events (source, event_type, timestamp);

-- -----------------------------------------------------------
-- Documents — ingested files with vector embeddings for RAG
-- -----------------------------------------------------------
-- Embedding dimension: 768 (nomic-embed-text via Ollama).
CREATE TABLE IF NOT EXISTS elmer.documents (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR,
    source_path     VARCHAR,
    title           VARCHAR,
    content         TEXT,
    content_type    VARCHAR,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(768),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ivfflat index for approximate nearest-neighbour cosine search.
-- lists=100 is a reasonable starting point; tune after data volume is known.
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON elmer.documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Unique index for autodoc upserts (ON CONFLICT).
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source_path
    ON elmer.documents (source, source_path)
    WHERE source IS NOT NULL AND source_path IS NOT NULL;

-- -----------------------------------------------------------
-- Transcriptions — Whisper speech-to-text results
-- -----------------------------------------------------------
-- Embedding dimension: 768 (nomic-embed-text via Ollama).
CREATE TABLE IF NOT EXISTS elmer.transcriptions (
    id                  SERIAL PRIMARY KEY,
    audio_file          VARCHAR,
    transcript          TEXT,
    segments            JSONB,
    language            VARCHAR,
    duration_seconds    FLOAT,
    model               VARCHAR,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding           vector(768),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Agent definitions — configurable AI agent personas
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS elmer.agent_definitions (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR NOT NULL UNIQUE,
    description     TEXT,
    system_prompt   TEXT,
    tools           JSONB,
    config          JSONB,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Conversations — chat history tied to agents
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS elmer.conversations (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER REFERENCES elmer.agent_definitions(id),
    channel         VARCHAR,
    messages        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- Notes — Obsidian/markdown notes with embeddings
-- -----------------------------------------------------------
-- Embedding dimension: 768 (nomic-embed-text via Ollama).
CREATE TABLE IF NOT EXISTS elmer.notes (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR,
    source_path     VARCHAR UNIQUE,
    title           VARCHAR,
    content         TEXT,
    tags            TEXT[],
    embedding       vector(768),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
