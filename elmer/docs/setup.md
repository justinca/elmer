# Elmer — Getting Started

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git
- PostgreSQL 15+ with pgvector extension (native on NUC)
- Mosquitto MQTT broker (existing Docker container)

## Initial Setup

1. **Clone the repository**

   ```bash
   git clone <your-repo-url> elmer
   cd elmer
   ```

2. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in:
   - Device IP addresses for your NUC, Windows PC, ShackPi, and WeatherPi
   - PostgreSQL credentials
   - MQTT credentials (user: w0abe, password: meshtastic)
   - Telegram bot token (from @BotFather)
   - Telegram allowed users (your chat ID)
   - Path to your Obsidian vault (if using knowledge base)
   - Ollama host (Windows machine IP)

   All Docker services share this single `.env` file. For local development,
   run `make sync-env` to symlink it into each package directory.

3. **Initialize the database**

   ```bash
   make init-db
   ```

   This creates the `elmer` schema, enables pgvector, and creates tables
   for events, documents, notes, transcriptions, and conversations.

4. **Start services**

   ```bash
   make up
   ```

   This builds and starts all 5 Docker containers:
   - `elmer-core` (port 8100) — API gateway
   - `elmer-dashboard` (port 8501) — Web UI
   - `elmer-telegram` — Telegram bot
   - `elmer-knowledge` — Obsidian sync scheduler
   - `elmer-transcription` — Audio file watcher

5. **Verify**

   ```bash
   make status
   ```

   Or run the full pipeline test:

   ```bash
   make test-pipeline
   ```

## Phase 2: Knowledge Pipeline Setup

The knowledge pipeline requires the Windows Worker to be running for:
- Ollama (LLM inference and embeddings via nomic-embed-text)
- Whisper (audio transcription)
- Obsidian vault access

### Windows Worker

On the Windows machine:

1. Install Python 3.11+
2. Install Ollama and pull models: `ollama pull llama3.1:8b && ollama pull nomic-embed-text`
3. Navigate to `packages/worker`
4. Run `run.bat`

### Knowledge Features

Once running, the system automatically:
- Ingests `docs/` directory on startup (auto, manual, and top-level .md files)
- Syncs Obsidian vault notes every hour
- Watches `audio/inbox/` for audio files to transcribe
- Re-generates system documentation every 6 hours

### Quick Commands

```bash
make search Q="system architecture"    # Semantic search
make chat M="What services run on the NUC?"  # RAG chat
make ingest-docs                       # Re-ingest documentation
make sync-notes                        # Trigger Obsidian sync
make transcribe F="recording.wav"      # Transcribe audio file
```

### Telegram Bot

Message your bot on Telegram:
- Send any text message for RAG-powered chat
- `/search <query>` — semantic search across all sources
- `/notes` — list recent Obsidian notes
- `/sources` — list knowledge sources
- `/help` — full command list

### Dashboard

Open http://localhost:8501 for the web dashboard:
- **System Status** — Node health, services, events
- **Knowledge Base** — Search, source management
- **Notes** — Obsidian notes browser
- **Transcriptions** — Audio upload and transcripts
- **Chat** — Web-based RAG chat

## Development

### Running a single package locally

```bash
cd packages/core
source ../../.venv/bin/activate   # or: source .venv/bin/activate
pip install -e ../common/ -e .
uvicorn src.main:app --reload --port 8100
```

### Running tests

```bash
make test           # Unit tests
make test-pipeline  # End-to-end pipeline verification
```

### Useful make targets

```bash
make up             # Build and start all services
make down           # Stop all services
make logs           # Tail all logs
make logs-core      # Tail core API logs
make logs-knowledge # Tail knowledge scheduler logs
make status         # Show container status + health checks
make db-shell       # PostgreSQL shell
make shell-core     # Shell into core container
make sync-env       # Symlink .env into packages for local dev
make clean          # Nuclear: remove all containers and images
```

## Project Layout

See [architecture.md](architecture.md) for the full system diagram,
knowledge pipeline details, and device inventory.
