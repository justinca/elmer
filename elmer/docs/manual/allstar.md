# AllStar Node — W0ABE (Node 68498)

## Overview

W0ABE operates AllStarLink node 68498 on a ShackPi (Raspberry Pi) at 192.168.1.65. AllStarLink is a VoIP-based amateur radio linking system built on Asterisk that connects repeaters and simplex nodes over the internet.

## Chat Commands

You can control the AllStar node through natural language in Elmer chat (dashboard or Telegram). Just type what you want to do:

### Status & Information

| What to say | What happens |
|-------------|-------------|
| "What's the AllStar status?" | Shows node online/offline, uptime, TX stats, connected nodes |
| "What nodes are we connected to?" | Lists currently linked nodes with callsigns and locations |
| "Look up node 2000" | Looks up any node in the AllStar directory |
| "What nodes are currently transmitting?" | Fetches the list of keyed/active nodes across the network |

### Connect & Disconnect

| What to say | What happens |
|-------------|-------------|
| "Connect to node 2000" | Connects to node 2000 in transceive (two-way) mode |
| "Monitor node 55555" | Connects in listen-only mode |
| "Disconnect from node 2000" | Disconnects from a specific node |
| "Disconnect from all nodes" | Disconnects from every currently connected node |

### Find & Connect

| What to say | What happens |
|-------------|-------------|
| "Find an active node and connect" | Fetches currently transmitting nodes, picks one at random, and connects |
| "Connect to the estes park pole hill node" | Searches the AllStar directory for "estes park", finds the Pole Hill node, and connects |
| "Search for nodes in Denver" | Searches the node directory by location and returns matching nodes |
| "Find a repeater in San Diego" | Searches by location and shows results with frequency, tone, site, and affiliation |

### Tips

- For location-based searches, use the city or region name. The system searches location, site name, callsign, and affiliation fields.
- You can ask follow-up questions like "connect to the first one" after a search.
- The node directory has over 14,000 active nodes with callsign, frequency, tone, location, site name, and affiliation data.
- Keyed/active nodes are those currently transmitting — this list changes constantly.

## Architecture

| Component | Details |
|-----------|---------|
| Node Number | 68498 |
| Callsign | W0ABE |
| Host | ShackPi (Raspberry Pi) at 192.168.1.65 |
| Software | AllStarLink 3 (ASL3) with Asterisk |
| Control | SSH from Elmer Core container via Asterisk CLI |
| DTMF Commands | *3=connect, *2=monitor, *1=disconnect, *70=local status |

## Data Sources

| Source | URL | Data |
|--------|-----|------|
| Stats API | stats.allstarlink.org/api/stats/68498 | Node stats, connections, uptime |
| Keyed Nodes | stats.allstarlink.org/stats/keyed | Currently transmitting nodes |
| Node Directory | allstarlink.org/nodelist/ | 14k+ nodes with location, site, affiliation |
| AllMon DB | allmondb.allstarlink.org/allmondb.php | Node directory (callsign, description, location) |

## Telegram

The `/allstar` Telegram command provides quick access to:
- `/allstar` or `/allstar status` — Node status
- `/allstar connect <node>` — Connect with confirmation button
- `/allstar disconnect <node>` — Disconnect with confirmation
- `/allstar monitor <node>` — Monitor with confirmation
- `/allstar lookup <node>` — Directory lookup

Regular chat messages in Telegram also support natural language AllStar control (same as dashboard chat).
