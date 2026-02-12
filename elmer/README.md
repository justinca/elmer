# Elmer — Personal AI Home Lab OS

> *In amateur radio, an **Elmer** is an experienced operator who mentors
> newcomers, patiently guiding them through the art and science of radio
> communication. This project carries that tradition forward — an AI-powered
> system that learns your home lab, anticipates your needs, and helps you
> master your station.*

Elmer is a self-hosted, AI-driven operating layer for managing an amateur
radio station, home automation, and personal infrastructure. It runs across
a small fleet of devices — a Linux NUC as the central hub, a Windows desktop
for GPU workloads, and Raspberry Pis for dedicated tasks — tied together with
MQTT, a shared knowledge base, and an agent framework.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Telegram Bot                      │
│                   (User Interface)                   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               Elmer Core (NUC)                       │
│         FastAPI Gateway · Port 8100                  │
│  ┌───────────┐ ┌───────────┐ ┌────────────────┐     │
│  │  Agents   │ │ Knowledge │ │  Orchestrator  │     │
│  └───────────┘ └───────────┘ └────────────────┘     │
│         │             │              │               │
│    ┌────▼─────────────▼──────────────▼────┐          │
│    │          MQTT / REST Bus              │          │
│    └──────────────────────────────────────┘          │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
   ┌──────▼──┐  ┌─────▼────┐ ┌────▼─────┐
   │ Windows │  │ ShackPi  │ │WeatherPi │
   │ Worker  │  │ (Radio)  │ │ (WX Stn) │
   │ GPU/LLM │  │          │ │          │
   └─────────┘  └──────────┘ └──────────┘
```

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your device IPs and credentials

# Start services
make up

# Check system health
make status
```

## Project Structure

| Package          | Description                              |
| ---------------- | ---------------------------------------- |
| `core`           | FastAPI gateway — central API hub        |
| `dashboard`      | Streamlit web dashboard                  |
| `worker`         | Windows GPU worker (LLM, transcription)  |
| `telegram-bot`   | Telegram bot interface                   |
| `agents`         | Agent framework and orchestrator         |
| `knowledge`      | RAG pipeline and document ingestion      |
| `transcription`  | Whisper speech-to-text pipeline          |
| `common`         | Shared utilities (MQTT, logging, types)  |

## Development

```bash
make build    # Build all containers
make up       # Start services
make down     # Stop services
make logs     # Tail logs
make test     # Run tests across packages
make status   # Health check all services
```

## License

Private project — not currently licensed for redistribution.

---

*73 de Elmer* 🔧📡
