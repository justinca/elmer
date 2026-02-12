# Elmer — Getting Started

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

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
   - Telegram bot token (from @BotFather)
   - Path to your Obsidian vault (if using knowledge base)

3. **Run setup script**

   ```bash
   bash scripts/setup.sh
   ```

   This creates Python virtual environments for each package.

4. **Start services**

   ```bash
   make up
   ```

5. **Verify**

   ```bash
   make status
   ```

## Development

### Running a single package locally

```bash
cd packages/core
source .venv/bin/activate
uvicorn src.main:app --reload --port 8100
```

### Running tests

```bash
make test
```

### Windows Worker

On the Windows machine:

1. Install Python 3.11+
2. Install Ollama
3. Navigate to `packages/worker`
4. Run `run.bat`

## Project Layout

See [architecture.md](architecture.md) for the full system diagram and
device inventory.
