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
| Band Scanner | Cron 0 13 UTC (6am MST) | Start HF band scanner | Enabled |
| Band Scanner Stop | Cron 0 4 UTC (9pm MST) | Stop scanner, send summary | Enabled |

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

## Band Scanner (`band-scanner` / `band-scanner-stop`)

Automated HF band scanner that controls SDR Console via virtual serial port
(com0com) on the Windows machine. Cycles through bands high-to-low, dwelling
on each band's FT8 calling frequency for 15 minutes (configurable).

**How it works:**
1. `band-scanner` agent starts the scanner at 6am MST (13:00 UTC) daily
2. Scanner selects daytime or nighttime bands based on UTC hour
3. Bands are prioritized by propagation conditions and DX spot activity
4. Radio is tuned via Kenwood TS-2000 CAT commands over virtual serial port to SDR Console
5. `band-scanner-stop` agent stops it at 9pm MST (04:00 UTC)

**Band lists:**
- **Daytime** (13:00–04:00 UTC): 10m, 12m, 15m, 17m, 20m (FT8 frequencies)
- **Nighttime** (04:00–13:00 UTC): 40m, 80m (FT8 frequencies)
- **Transition** (±2 hours around boundaries): 20m and 40m added to both

**FT8 calling frequencies:**
- 10m: 28.074 MHz, 12m: 24.915 MHz, 15m: 21.074 MHz
- 17m: 18.100 MHz, 20m: 14.074 MHz, 40m: 7.074 MHz, 80m: 3.573 MHz

**Band prioritization:**
1. Fetches propagation conditions from Core `/propagation/bands`
2. Fetches DX spot counts from Core `/dx/spots/summary`
3. Orders: good+active > good+quiet > fair+active > fair+quiet > poor
4. Within each group, maintains high-to-low frequency order
5. Order is rebuilt after each full cycle

**Manual tune detection:** If someone changes the frequency manually (more
than 5 kHz from expected), the scanner pauses automatically and publishes
an MQTT notification to `elmer/radio/scanner-paused`.

**Setup (com0com virtual serial port):**
1. Create a com0com port pair (e.g. COM10 ↔ COM11)
2. In SDR Console → Options → CAT to Radio: select COM10, 57600 baud, Kenwood TS-2000
3. Set `CAT_COM_PORT=COM11` in Worker .env (the other end of the pair)

**Configuration (Worker .env):**
```
CAT_COM_PORT=COM11            # Virtual COM port (com0com) to SDR Console
CAT_BAUD_RATE=57600           # Baud rate for CAT serial port
SCANNER_DWELL_SECONDS=900     # Default dwell time (15 min)
SCANNER_DAYTIME_START_UTC=13  # 6am MST
SCANNER_DAYTIME_END_UTC=4     # 9pm MST
SCANNER_AUTO_START=false      # Auto-start on Worker boot
```

**Control via Telegram:**
- `/scan` — show scanner status (band, time remaining, order)
- `/scan start` — start scanning
- `/scan stop` — stop scanning
- `/scan pause` — pause on current band
- `/scan resume` — resume scanning
- `/scan next` — skip to next band

**Control via API:**
```bash
# Start/stop
curl -X POST http://localhost:8100/radio/scanner/start
curl -X POST http://localhost:8100/radio/scanner/stop

# Status
curl http://localhost:8100/radio/scanner/status

# Pause/resume/next
curl -X POST http://localhost:8100/radio/scanner/pause
curl -X POST http://localhost:8100/radio/scanner/resume
curl -X POST http://localhost:8100/radio/scanner/next

# Change dwell time
curl -X POST http://localhost:8100/radio/scanner/dwell -d '{"seconds": 600}'
```

**Tune radio directly:**
- `/tune 14074` — tune to 14074 kHz
- `/band 20m` — tune to 20m FT8 frequency (14.074 MHz)
- API: `POST /radio/frequency {"frequency_hz": 14074000}`
- API: `POST /radio/mode {"mode": "USB"}`

**Dashboard:** The Radio Control page shows scanner status, controls,
scan order with propagation condition badges and DX spot activity bars,
and a dwell time slider.

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
| `/scan` | Band scanner status |
| `/scan start` | Start band scanner |
| `/scan stop` | Stop band scanner |
| `/scan pause` | Pause on current band |
| `/scan resume` | Resume scanning |
| `/scan next` | Skip to next band |
| `/tune <freq_khz>` | Tune radio to frequency (e.g. `/tune 14074`) |
| `/band <band>` | Tune to band FT8 frequency (e.g. `/band 20m`) |
