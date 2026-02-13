# Agent System

The Elmer agent system enables autonomous AI agents that respond to MQTT messages, scheduled timers, system events, and API calls. Agents execute via Ollama with tool-calling capabilities and route output to Telegram, MQTT, and logs.

## Architecture

```
Triggers (MQTT / Schedule / Event / API)
    │
    ▼
Orchestrator (queue + 3 workers)
    │
    ▼
Executor (Ollama tool-calling loop, max 10 rounds)
    │
    ▼
OutputRouter (telegram / mqtt / dashboard / log)
```

### Components

| Component | Location | Role |
|---|---|---|
| Registry | `packages/agents/src/registry.py` | CRUD for agent definitions in DB |
| Orchestrator | `packages/agents/src/orchestrator.py` | Trigger management, queue, worker pool |
| Executor | `packages/agents/src/executor.py` | Ollama API calls, tool dispatch, timeout |
| OutputRouter | `packages/agents/src/output_router.py` | Delivers results to channels |
| ToolRegistry | `packages/agents/src/tools/` | Tool implementations agents can call |

### YAML Sync

Agent definitions are YAML files in `packages/agents/agent_definitions/`. On startup, the system syncs these to the `elmer.agent_definitions` table. Changes to YAML files take effect on restart or via the reload API.

## Agent Definitions

Each agent is a YAML file with this structure:

```yaml
name: my-agent                    # Unique identifier (URL-safe)
display_name: My Agent            # Human-readable name
description: What this agent does
model: llama3.1:8b                # Ollama model

system_prompt: >                  # Instructions for the LLM
  You are a helpful agent...

tools:                            # Tools the agent can call
  - name: search_knowledge
    description: Search the knowledge base
    config:
      sources: [docs, notes]

triggers:                         # What activates the agent
  - type: schedule
    cron: "0 7 * * *"
  - type: mqtt
    topic: "some/topic/#"
    config:
      debounce_seconds: 30

output_channels: [telegram, log]  # Where results go
enabled: true
max_concurrent: 1                 # Parallel execution limit
timeout_seconds: 120              # Kill after this long
```

## Available Tools

| Tool | Description |
|---|---|
| `search_knowledge` | Semantic search across docs, notes, transcripts |
| `query_database` | SQL queries against allowed Elmer tables |
| `send_telegram` | Send a message to the admin's Telegram |
| `publish_mqtt` | Publish to MQTT topics (configurable prefix whitelist) |
| `call_api` | Make HTTP requests to internal services |
| `run_script` | Execute scripts from `scripts/agent-scripts/` |

## Trigger Types

### MQTT

Fires when a message arrives on the matching topic. Supports wildcards (`+`, `#`). Optional debounce prevents rapid re-triggering.

```yaml
triggers:
  - type: mqtt
    topic: "homeassistant/+/+/state"
    config:
      debounce_seconds: 60
```

### Schedule

Fires on a cron schedule or at a fixed interval.

```yaml
triggers:
  - type: schedule
    cron: "0 7 * * *"          # Daily at 7am
  - type: schedule
    interval_seconds: 300       # Every 5 minutes
```

### Event

Fires when a system event (like `node_offline`) is published to MQTT.

```yaml
triggers:
  - type: event
    event_type: node_offline
```

### API

All agents can be triggered via `POST /agents/{name}/run` regardless of other triggers.

## Current Agents

| Agent | Triggers | Purpose |
|---|---|---|
| `daily-briefing` | Cron 7am | Morning system status + weather + bands |
| `weekly-digest` | Cron Sunday 6pm | Weekly analytical summary |
| `node-watchdog` | Event + 5min interval | Node health monitoring |
| `allstar-monitor` | 10min interval + MQTT heartbeat | AllStar/Asterisk status |
| `home-assistant-reactor` | MQTT HA state changes | Smart home event evaluation |
| `meshtastic-responder` | MQTT meshtastic/received/# | Respond to mesh messages |
| `knowledge-curator` | Cron 2am | Knowledge base maintenance |
| `radio-assistant` | MQTT | Ham radio Q&A |
| `system-monitor` | 5min interval | System health checks |

## Safety Features

### Circuit Breaker

If an agent fails 5 consecutive times, it is automatically disabled and an alert is published to `elmer/alerts/agent`. Re-enable via API or Telegram `/enable <name>`.

### Rate Limiting

Each agent is limited to 60 executions per hour. Excess triggers are dropped with a warning log.

### Timeout Enforcement

Two layers: semaphore acquisition timeout and execution timeout, both using the agent's `timeout_seconds` setting.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/agents` | List all agents |
| POST | `/agents` | Create a new agent |
| GET | `/agents/{name}` | Get agent details |
| PUT | `/agents/{name}` | Update an agent |
| DELETE | `/agents/{name}` | Delete an agent |
| POST | `/agents/{name}/enable` | Enable an agent |
| POST | `/agents/{name}/disable` | Disable an agent |
| POST | `/agents/{name}/run` | Trigger a manual run |
| GET | `/agents/{name}/runs` | List runs for an agent |
| GET | `/agents/runs` | List all agent runs |
| GET | `/agents/tools` | List available tools |
| GET | `/agents/schedule` | List scheduled jobs |
| GET | `/agents/orchestrator/status` | Orchestrator status |
| POST | `/agents/orchestrator/reload` | Reload all agents |

## Telegram Commands

| Command | Description |
|---|---|
| `/agents` | List all agents with status |
| `/agent <name>` | Detailed info with action buttons |
| `/run <name> [input]` | Manually trigger an agent |
| `/enable <name>` | Enable an agent |
| `/disable <name>` | Disable an agent |
| `/runs [name]` | Recent agent runs |
| `/schedule` | Scheduled agent jobs |

## Makefile Commands

```bash
make agents          # List all agents
make agent-run A=daily-briefing  # Trigger a run
make agent-logs A=node-watchdog  # Recent runs for an agent
make agent-reload    # Reload all agent definitions
make test-agents     # Run end-to-end agent tests
```

## MQTT Topics

| Topic | Direction | Description |
|---|---|---|
| `elmer/agents/{name}/triggered` | Published | Agent execution started |
| `elmer/agents/{name}/completed` | Published | Agent execution finished |
| `elmer/agents/{name}/output` | Published | Agent output data |
| `elmer/orchestrator/status` | Published | Orchestrator status on start |
| `elmer/orchestrator/metrics` | Published | Metrics every 60s |
| `elmer/alerts/agent` | Published | Circuit breaker alerts |

## Adding a New Agent

1. Create a YAML file in `packages/agents/agent_definitions/`:
   ```bash
   vi packages/agents/agent_definitions/my-agent.yaml
   ```

2. Follow the schema (see Agent Definitions above).

3. Reload the orchestrator:
   ```bash
   curl -X POST http://localhost:8100/agents/orchestrator/reload
   ```

4. Test with a manual trigger:
   ```bash
   curl -X POST http://localhost:8100/agents/my-agent/run
   ```

5. Check results:
   ```bash
   curl http://localhost:8100/agents/my-agent/runs?limit=1
   ```
