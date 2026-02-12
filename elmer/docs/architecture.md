# Elmer — System Architecture

## Overview

Elmer runs as a distributed system across a small fleet of devices connected
via the local network. The NUC serves as the central hub, running the core
API gateway, agent framework, and most containerized services. The Windows
desktop handles GPU-heavy workloads (LLM inference, transcription). Raspberry
Pis serve dedicated roles at the radio station and weather station.

## Architecture Diagram

```
                        ┌──────────────────────┐
                        │     Telegram Bot      │
                        │   (Cloud → Webhook)   │
                        └──────────┬───────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                        NUC (Hub)                                 │
│                    192.168.x.NUC                                 │
│                                                                  │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌─────────────┐   │
│  │   Core   │  │ Dashboard │  │ Knowledge  │  │Transcription│   │
│  │  :8100   │  │   :8501   │  │ (RAG Sync) │  │  (Watcher)  │   │
│  └────┬─────┘  └───────────┘  └──────┬──────┘  └──────┬──────┘   │
│       │                             │                │           │
│  ┌────▼─────────────────────────────▼────────────────▼────────┐  │
│  │                     MQTT Bus (:1883)                       │  │
│  └────┬──────────────────┬───────────────────┬───────────────┘  │
│       │                  │                   │                   │
│  ┌────▼─────┐  ┌────────▼────────┐  ┌──────▼──────┐            │
│  │ Postgres │  │    Mosquitto    │  │   pgvector  │            │
│  │  :5432   │  │     :1883      │  │  (768-dim)  │            │
│  └──────────┘  └────────────────┘  └─────────────┘            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┼─────────────┐
              │            │             │
     ┌────────▼───┐  ┌────▼─────┐  ┌────▼──────┐
     │  Windows   │  │ ShackPi  │  │ WeatherPi │
     │  Desktop   │  │  (RPi)   │  │   (RPi)   │
     │ 192.168.x. │  │ 192.168. │  │ 192.168.  │
     │   WIN      │  │  x.SHACK │  │  x.WX     │
     │            │  │          │  │           │
     │ Worker API │  │ Rig Ctrl │  │ WX Stn   │
     │   :8101    │  │ WSJT-X   │  │ Sensors  │
     │ Ollama GPU │  │ Logging  │  │ MQTT Pub  │
     │ Whisper    │  │          │  │           │
     └────────────┘  └──────────┘  └───────────┘
```

## Device Inventory

| Device           | Role       | IP Address         | OS             | Key Services                                      |
| ---------------- | ---------- | ------------------ | -------------- | ------------------------------------------------- |
| **NUC**          | Hub        | `192.168.x.NUC`   | Ubuntu/Debian  | Core API, Dashboard, Knowledge, Transcription, DB |
| **Windows PC**   | GPU Worker | `192.168.x.WIN`   | Windows 10/11  | Worker API, Ollama (GPU), Whisper, Obsidian        |
| **ShackPi**      | Radio      | `192.168.x.SHACK` | Raspberry Pi OS| Rig control, WSJT-X, QSO logging, MQTT publish    |
| **WeatherPi**    | Sensor     | `192.168.x.WX`    | Raspberry Pi OS| Weather station, sensors, MQTT publish             |

## Docker Services (NUC)

| Container            | Package              | Port  | Purpose                           |
| -------------------- | -------------------- | ----- | --------------------------------- |
| `elmer-core`         | `packages/core`      | 8100  | REST API gateway (FastAPI)        |
| `elmer-dashboard`    | `packages/dashboard` | 8501  | Web UI (Streamlit)                |
| `elmer-telegram`     | `packages/telegram-bot` | —  | Telegram chat interface           |
| `elmer-knowledge`    | `packages/knowledge` | —     | Obsidian sync + doc ingestion     |
| `elmer-transcription`| `packages/transcription` | — | Audio file watcher + pipeline     |

All containers use `network_mode: host` and share `~/elmer/.env`.

## Knowledge Pipeline (Phase 2)

```
                  ┌──────────────┐
                  │   Obsidian   │  (Windows, via Worker API)
                  │    Vault     │
                  └──────┬───────┘
                         │ /obsidian/notes
                         ▼
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│  Elmer Docs │──→│  Chunking &  │──→│  pgvector    │
│  (auto/     │   │  Embedding   │   │  (768-dim)   │
│   manual/)  │   │  nomic-embed │   │  cosine sim  │
└─────────────┘   └──────────────┘   └──────┬───────┘
                                            │
┌─────────────┐   ┌──────────────┐          │
│   Audio     │──→│   Whisper    │──→ embed ─┤
│   Files     │   │  (Worker)    │          │
└─────────────┘   └──────────────┘          │
                                            ▼
                                     ┌──────────────┐
                                     │  RAG Search  │
                                     │  + LLM Chat  │
                                     └──────────────┘
```

### Data Flow

1. **Documents**: Markdown files in `docs/` are chunked, embedded (nomic-embed-text, 768 dims), and stored in `elmer.documents` with pgvector.
2. **Notes**: Obsidian vault notes are synced via the Worker API, embedded, and stored in `elmer.notes`.
3. **Transcriptions**: Audio files dropped in `audio/inbox/` are transcribed by Whisper on the Worker, embedded, and stored in `elmer.transcriptions`.
4. **Search**: Queries are embedded and compared via cosine similarity across all three tables.
5. **Chat**: RAG chat retrieves relevant context from search, builds a prompt with conversation history, and generates responses via Ollama (llama3.1:8b).

### Scheduler

Core runs a unified scheduler for periodic tasks:
- **autodoc-regen**: Regenerate system docs (every 6 hours)
- **ingest-docs**: Re-embed Elmer docs (every 6 hours, on startup)

Knowledge container runs its own scheduler:
- **Obsidian sync**: Incremental sync (every 1 hour)
- **Doc re-ingestion**: Re-embed changed docs (every 1 hour)

## Communication

- **REST**: Core API ↔ Worker API for synchronous requests (LLM, transcription)
- **MQTT**: All devices publish/subscribe for async events and telemetry
  - `elmer/+/heartbeat` — Node heartbeats with system metrics
  - `elmer/+/status` — Service health status (retained)
  - `elmer/events/#` — System events
  - `elmer/transcription/result` — Completed transcriptions
  - `elmer/knowledge/obsidian/sync` — Sync results
  - `elmer/scheduler/{task}` — Scheduled task results
- **PostgreSQL**: Persistent storage for events, knowledge base, conversations

## Package Dependency Graph

```
telegram-bot ──→ core ──→ common
dashboard    ──→ core ──→ common
                  │
                  ├──→ knowledge ──→ common
                  └──→ worker (remote, via REST)
                         │
                         └──→ Ollama, Whisper
```

## Ports

| Port  | Service            | Device     |
| ----- | ------------------ | ---------- |
| 8100  | Elmer Core API     | NUC        |
| 8101  | Elmer Worker API   | Windows PC |
| 8501  | Streamlit Dashboard| NUC        |
| 5432  | PostgreSQL         | NUC        |
| 1883  | MQTT (Mosquitto)   | NUC        |
| 11434 | Ollama             | Windows PC |
