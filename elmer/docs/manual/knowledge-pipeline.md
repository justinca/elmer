# Knowledge Pipeline Guide

## Overview

The Elmer knowledge pipeline ingests documents, Obsidian vault notes, and
audio transcriptions into a unified search index powered by PostgreSQL
pgvector. This enables RAG-powered chat and semantic search across all
knowledge sources.

## How It Works

### Embedding

All text is embedded using the `nomic-embed-text` model (768 dimensions)
via Ollama on the Windows Worker. The embedding process:

1. Text is chunked (default 500 chars, markdown-aware header splitting)
2. Each chunk is sent to the Worker API (`/llm/embed`) or Ollama direct
3. The resulting 768-dim vector is stored alongside the text in pgvector
4. Search uses cosine similarity to find relevant chunks

### Storage Tables

| Table | Content | Key Columns |
|---|---|---|
| `elmer.documents` | Docs, manuals, auto-generated files | `source`, `source_path`, `content`, `embedding` |
| `elmer.notes` | Obsidian vault notes | `source_path`, `content`, `tags`, `embedding` |
| `elmer.transcriptions` | Audio transcripts | `audio_file`, `transcript`, `segments`, `embedding` |

### RAG Chat Flow

1. User sends a message (via Telegram, Dashboard, or API)
2. The query is embedded and searched across all three tables
3. Top-scoring results are assembled as context
4. Context + conversation history + user message are sent to Ollama (llama3.1:8b)
5. Response includes source attribution

## Adding New Knowledge Sources

### Via API (Recommended)

**Ingest a single file:**
```bash
curl -X POST http://localhost:8100/knowledge/ingest/file \
  -F "file=@path/to/document.md" \
  -F "source=my-source"
```

**Ingest raw text:**
```bash
curl -X POST http://localhost:8100/knowledge/ingest/text \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Your text content here",
    "title": "Document Title",
    "source": "my-source",
    "metadata": {"category": "notes"}
  }'
```

**Ingest a directory:**
```bash
curl -X POST http://localhost:8100/knowledge/ingest/directory \
  -H 'Content-Type: application/json' \
  -d '{
    "path": "/app/docs",
    "source": "elmer-docs",
    "recursive": true,
    "patterns": ["*.md", "*.txt"]
  }'
```

### Via Make Commands

```bash
make ingest-docs                    # Re-ingest Elmer's own docs
make search Q="system architecture" # Search across all sources
make chat M="What is Elmer?"        # RAG-powered chat
```

### Via Telegram Bot

- `/search <query>` — Semantic search with score bars
- `/sources` — List all knowledge sources with counts
- `/sync` — Trigger doc re-ingestion
- Send any text message for RAG-powered conversation

### Adding Files to Auto-Ingest

Place files in these directories for automatic ingestion:

| Directory | Source Name | Description |
|---|---|---|
| `docs/auto/` | `elmer-autodoc` | Auto-generated system docs (status, config, etc.) |
| `docs/manual/` | `elmer-manual` | Manually written documentation |
| `docs/*.md` | `elmer-docs` | Top-level architecture/setup docs |

The scheduler re-ingests these every 6 hours, skipping unchanged files.

## Triggering Syncs

### Obsidian Vault Sync

The knowledge container syncs Obsidian notes every hour via the Worker API.
To trigger manually:

```bash
# Full sync (fetch all notes, compare, upsert/delete)
curl -X POST http://localhost:8100/notes/sync

# Incremental sync (only changes since last sync)
curl -X POST http://localhost:8100/notes/sync/incremental
```

Or via Telegram: `/sync`

### Audio Transcription

Drop audio files in `~/elmer/audio/inbox/`. The transcription watcher
picks them up, sends to Whisper on the Worker, stores the transcript with
embeddings, and moves the file to `audio/processed/`.

Supported formats: `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.webm`

Or upload via API:
```bash
make transcribe F="recording.wav"
```

## Search Endpoints

### Unified Search (across all sources)

```bash
curl -X POST http://localhost:8100/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "your search query",
    "sources": ["docs", "notes", "transcripts"],
    "limit": 10,
    "threshold": 0.5
  }'
```

Source names: `docs` (documents), `notes` (Obsidian), `transcripts` (audio)

### Note-Specific Search

```bash
curl http://localhost:8100/notes/search?q=your+query&limit=5
```

### Transcription Search

```bash
curl http://localhost:8100/transcription/search?q=your+query&limit=5
```

### List Sources

```bash
curl http://localhost:8100/knowledge/sources
```

### Delete a Source

```bash
curl -X DELETE http://localhost:8100/knowledge/source/my-source
```

## Telegram Knowledge Commands

| Command | Description |
|---|---|
| `/search <query>` | Semantic search across all sources |
| `/notes` | List recent Obsidian notes |
| `/note <id>` | View a specific note |
| `/sources` | List knowledge sources with counts |
| `/sync` | Trigger doc re-ingestion |
| `/transcripts` | List recent transcriptions |
| `/transcript <id>` | View a full transcript |
| `/tsearch <query>` | Search transcriptions |
| Any text message | RAG-powered chat conversation |

## Monitoring

### Scheduler Status

```bash
curl http://localhost:8100/health/scheduler
```

Returns status of all scheduled tasks with run counts and timing.

### MQTT Topics

Subscribe to knowledge events:
- `elmer/knowledge/obsidian/sync` — Vault sync results
- `elmer/transcription/result` — New transcriptions
- `elmer/scheduler/#` — All scheduler task results

### Logs

```bash
make logs-core          # Core API logs (search, ingest, chat)
make logs-knowledge     # Knowledge scheduler (sync, ingest)
make logs-transcription # Transcription watcher
```
