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
│  │   Core   │  │ Dashboard │  │   Agents   │  │  Knowledge  │   │
│  │  :8100   │  │   :8501   │  │            │  │    (RAG)    │   │
│  └────┬─────┘  └───────────┘  └─────┬──────┘  └──────┬──────┘   │
│       │                             │                │           │
│  ┌────▼─────────────────────────────▼────────────────▼────────┐  │
│  │                     MQTT Bus (:1883)                       │  │
│  └────┬──────────────────┬───────────────────┬───────────────┘  │
│       │                  │                   │                   │
│  ┌────▼─────┐  ┌────────▼────────┐  ┌──────▼──────┐            │
│  │ Postgres │  │    Mosquitto    │  │   Ollama    │            │
│  │  :5432   │  │     :1883      │  │   :11434    │            │
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
| **NUC**          | Hub        | `192.168.x.NUC`   | Ubuntu/Debian  | Core API, Dashboard, Agents, Knowledge, MQTT, DB  |
| **Windows PC**   | GPU Worker | `192.168.x.WIN`   | Windows 10/11  | Worker API, Ollama (GPU), Whisper, LLM inference   |
| **ShackPi**      | Radio      | `192.168.x.SHACK` | Raspberry Pi OS| Rig control, WSJT-X, QSO logging, MQTT publish    |
| **WeatherPi**    | Sensor     | `192.168.x.WX`    | Raspberry Pi OS| Weather station, sensors, MQTT publish             |

## Communication

- **REST**: Core API ↔ Worker API for synchronous requests (LLM, transcription)
- **MQTT**: All devices publish/subscribe for async events and telemetry
  - `elmer/status/#` — Service health heartbeats
  - `elmer/radio/#` — Band conditions, QSO events
  - `elmer/weather/#` — Temperature, humidity, pressure, wind
  - `elmer/home/#` — Home automation events
- **PostgreSQL**: Persistent storage for logs, knowledge base metadata, QSOs

## Package Dependency Graph

```
telegram-bot ──→ core ──→ common
dashboard    ──→ core ──→ common
agents       ──→ core ──→ common
                  │
                  ├──→ knowledge ──→ common
                  └──→ worker (remote, via REST)
                         │
                         └──→ transcription (models shared)
```

## Ports

| Port  | Service           | Device     |
| ----- | ----------------- | ---------- |
| 8100  | Elmer Core API    | NUC        |
| 8101  | Elmer Worker API  | Windows PC |
| 8501  | Streamlit Dashboard| NUC       |
| 5432  | PostgreSQL        | NUC        |
| 1883  | MQTT (Mosquitto)  | NUC        |
| 11434 | Ollama            | Windows PC |
