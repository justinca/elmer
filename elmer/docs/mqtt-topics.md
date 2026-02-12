# Elmer MQTT Topic Structure

All Elmer MQTT messages live under the `elmer/` prefix.
Payloads are always JSON unless noted otherwise.

## Node Status & Heartbeats

Each node publishes a **retained** status message and a **periodic
heartbeat** (default every 30 s).

| Topic | Publisher | Retained | Description |
|---|---|---|---|
| `elmer/core/status` | Core | Yes | `"online"` / `"offline"` |
| `elmer/core/heartbeat` | Core | No | Periodic heartbeat w/ system metrics |
| `elmer/worker/status` | Worker | Yes | `"online"` / `"offline"` |
| `elmer/worker/heartbeat` | Worker | No | Periodic heartbeat w/ system metrics |
| `elmer/shackpi/status` | ShackPi | Yes | `"online"` / `"offline"` |
| `elmer/shackpi/heartbeat` | ShackPi | No | Periodic heartbeat w/ system metrics |
| `elmer/weatherpi/status` | WeatherPi | Yes | `"online"` / `"offline"` |
| `elmer/weatherpi/heartbeat` | WeatherPi | No | Periodic heartbeat w/ system metrics |

### Heartbeat Payload

```json
{
  "node": "core",
  "status": "online",
  "uptime_seconds": 86400,
  "timestamp": "2026-02-12T14:30:00+00:00",
  "details": {
    "platform": "Linux",
    "hostname": "nuc",
    "cpu_percent": 12.3,
    "ram_total_mb": 16384,
    "ram_used_mb": 8192,
    "ram_percent": 50.0,
    "disk_total_gb": 500.0,
    "disk_used_gb": 120.5,
    "disk_percent": 24.1,
    "system_uptime_seconds": 604800
  }
}
```

### Status Values

| Value | Meaning |
|---|---|
| `online` | Node is healthy and publishing heartbeats |
| `degraded` | Node is up but a subsystem is impaired |
| `offline` | Node published a clean shutdown |
| `unreachable` | Core has not received heartbeats (3x missed interval) |

## System Events

General-purpose event bus. Events are also persisted to the
`elmer.events` database table by Core.

| Topic | Description |
|---|---|
| `elmer/events/{source}/{type}` | Structured event from any source |

### Event Payload

```json
{
  "source": "core",
  "event_type": "node_unreachable",
  "data": { "node": "worker" },
  "timestamp": "2026-02-12T14:30:00+00:00"
}
```

## Knowledge & RAG (Phase 2)

| Topic | Publisher | Description |
|---|---|---|
| `elmer/knowledge/obsidian/sync` | Core / Knowledge | Obsidian vault sync results |
| `elmer/knowledge/sync` | Knowledge | General knowledge sync notification |
| `elmer/transcription/result` | Core / Transcription | Completed transcription with metadata |
| `elmer/scheduler/{task_name}` | Core Scheduler | Scheduled task execution result |

### Obsidian Sync Payload

```json
{
  "event": "full_sync",
  "added": 5,
  "updated": 2,
  "deleted": 0,
  "unchanged": 43,
  "errors": 0,
  "duration_seconds": 12.5,
  "timestamp": "2026-02-12T14:30:00+00:00"
}
```

### Transcription Result Payload

```json
{
  "id": 42,
  "audio_file": "recording.wav",
  "transcript": "First 500 characters of the transcription...",
  "language": "en",
  "duration_seconds": 120.5
}
```

### Scheduler Task Payload

```json
{
  "task": "ingest-docs",
  "status": "ok",
  "duration_seconds": 3.45,
  "run_count": 12,
  "timestamp": "2026-02-12T14:30:00+00:00",
  "result": {
    "ingested": 8,
    "skipped": 3,
    "errors": []
  }
}
```

## Agents

| Topic | Description |
|---|---|
| `elmer/agents/{agent_id}/status` | Agent online/offline/busy |
| `elmer/agents/{agent_id}/output` | Agent output / results |

## Chat

| Topic | Description |
|---|---|
| `elmer/chat/request` | Incoming chat message (from Telegram, etc.) |
| `elmer/chat/response` | Chat response to deliver back to user |

## Subscription Patterns

Useful wildcard subscriptions:

| Pattern | Matches |
|---|---|
| `elmer/+/heartbeat` | All node heartbeats |
| `elmer/+/status` | All node status messages |
| `elmer/events/#` | All system events |
| `elmer/knowledge/#` | All knowledge/sync events |
| `elmer/scheduler/#` | All scheduler task results |
| `elmer/agents/#` | All agent traffic |
| `elmer/#` | Everything |
