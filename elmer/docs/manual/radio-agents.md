# Radio Agents

Elmer includes several agents focused on amateur radio intelligence. These run
on schedule or on-demand to provide propagation alerts, DX notifications, POTA
planning, and contest coaching.

## Agent Overview

| Agent | Schedule | Purpose | Default |
|-------|----------|---------|---------|
| DX Spotter | MQTT trigger | Alert on needed DX entities | Enabled |
| POTA Advisor | Sat 7am | Weekend activation briefing | Enabled |
| Contest Coach | Every 30 min | Live contest rate/score coaching | Disabled |
| Band Monitor | Every 30 min (13Z-03Z) | HF band opening/closing alerts | Disabled |
| Radio Assistant | On-demand | Ham radio knowledge assistant | Enabled |

## DX Spotter (`dx-spotter`)

Monitors DX cluster spots and alerts when a spot matches your needs list.

**How it works:**
1. Triggered via MQTT on `elmer/dx/spot` (debounced 60s per callsign)
2. Checks the spot against the needs list in PostgreSQL
3. Evaluates propagation conditions for the spotted band
4. Sends Telegram alert for priority 1-2 (RED) and priority 3-4 (YELLOW) needs
5. Green/routine spots are logged but not alerted

**Configure:**
- Maintain your needs list via the DX Spots dashboard page or `/need` Telegram command
- Priority 1-2 = rare/needed, 3-4 = notable, 5 = routine

## POTA Advisor (`pota-advisor`)

Saturday morning briefing for POTA activation planning.

**Briefing includes:**
1. Propagation outlook for the day
2. 3-5 nearby parks (within configured radius)
3. Band and time recommendations
4. Current activator spots for park-to-park contacts
5. Quick tips (weather, battery, logging)

**Configure:**
```yaml
config:
  home_grid: "DN70"
  radius_miles: 50
```

**Trigger manually:**
```bash
make agent-run A=pota-advisor
```

## Contest Coach (`contest-coach`)

Real-time coaching during contests. Disabled by default — enable before a contest.

**Features:**
- Detects active contest QSOs from Log4OM
- Reports rate (10 min and 60 min windows), multipliers, estimated score
- Suggests band changes based on propagation
- Only messages when contest activity detected in the last hour
- Silent when no contest is active

**Enable for a contest:**
```bash
# Via Makefile
make agent-run A=contest-coach

# Via API
curl -X POST http://localhost:8100/agents/contest-coach/enable
```

**Disable after contest:**
```bash
curl -X POST http://localhost:8100/agents/contest-coach/disable
```

## Band Monitor (`band-monitor`)

Monitors HF band conditions and alerts on significant changes. Disabled by default.

**Alert criteria (selective — only notable changes):**
- Major band (20m/15m/10m) goes from Poor/Fair to Good
- K-index rises above 4 (geomagnetic storm)
- Rare high-band opening (10m/6m going Good)
- Multiple bands degrading simultaneously

**Active hours:** 13Z-03Z (Colorado daylight roughly)

**Publishes to MQTT:** `elmer/radio/band-report` for other agents to consume.

**Enable:**
```bash
curl -X POST http://localhost:8100/agents/band-monitor/enable
```

## Radio Assistant (`radio-assistant`)

General-purpose ham radio knowledge assistant. Available via chat or API.

**Station knowledge built in:**
- Callsign: W0ABE, Grid: DN70
- Radios: IC-7300, FT-DX10, FT-710 Field
- Antenna: DX Commander (multi-band vertical)
- Can query live propagation, POTA, DX, and log data

**Trigger:** Send a radio question via Telegram chat, or:
```bash
make agent-run A=radio-assistant
```

## Daily Briefing Integration

The daily briefing agent (`daily-briefing`, 7am daily) now includes:
- **Propagation:** SFI, K-index, which bands are open
- **DX Activity:** Overnight spot stats, rare DX spotted
- **QSO Count:** Current log totals

## Telegram Commands

All radio data is accessible via Telegram:

| Command | Description |
|---------|-------------|
| `/prop` | Propagation summary per band |
| `/bands` | Compact band conditions grid |
| `/solar` | Solar indices (SFI, SSN, K-index) |
| `/spots [band] [mode]` | Recent DX spots |
| `/dx <call>` | DXCC entity lookup |
| `/needs` | Show needs list |
| `/need <entity> [band] [mode]` | Add to needs list |
| `/pota [park_id]` | POTA spots or park info |
| `/plan <park_id>` | Activation plan |
| `/log` | QSO summary |
| `/dxcc` | DXCC award progress |
| `/contest` | Upcoming contests |
