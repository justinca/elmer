# Radio Equipment Setup

## Station — W0ABE (DN70, Northern Colorado)

### Equipment

| Item | Model | Connection | Notes |
|------|-------|------------|-------|
| HF Transceiver | Icom IC-7300 | USB (CI-V + audio) | Primary — FT8/FT4, general HF |
| HF Transceiver | Yaesu FT-DX10 | USB (CAT + audio) | Secondary — SSB contesting |
| Portable Transceiver | Yaesu FT-710 Field | USB | POTA activations |
| Antenna | DX Commander | Coax (SO-239) | Multi-band vertical |
| Power Supply | | 13.8V DC | |

### Software

| Application | Purpose | Host | Config Location |
|-------------|---------|------|-----------------|
| Log4OM | QSO Logging | Windows Desktop | AppData/Log4OM |
| WSJT-X | FT8/FT4 | Windows Desktop | AppData/WSJT-X |
| JS8Call | JS8 | Windows Desktop | AppData/JS8Call |
| Elmer Worker | Log proxy, DX cluster | Windows Desktop | packages/worker/.env |
| Elmer Core | API, propagation, POTA | NUC (Docker) | packages/core/.env |
| Elmer Dashboard | Streamlit UI | NUC (Docker) | packages/dashboard/.env |

### Frequencies & Modes

| Band | Frequency | Mode | Notes |
|------|-----------|------|-------|
| 20m | 14.074 MHz | FT8 | Primary digital — best propagation |
| 40m | 7.074 MHz | FT8 | Evening digital |
| 20m | 14.300 MHz | SSB | Maritime mobile net |
| 40m | 7.200 MHz | SSB | Ragchew |
| 15m | 21.074 MHz | FT8 | Good openings when SFI > 120 |
| 10m | 28.074 MHz | FT8 | Solar max — check K-index |

## Elmer Integration

### DX Cluster

The worker connects to a DX cluster telnet server and forwards spots:
- Worker fetches spots from the cluster and caches in memory
- Core proxies `/dx/spots` and `/dx/summary` to the worker
- New spots are published to MQTT `elmer/dx/spot` for the DX Spotter agent
- Needs list stored in PostgreSQL, matched against incoming spots

### Log4OM Integration

The worker reads the Log4OM SQLite database directly:
- `/log4om/stats` — QSO totals, band/mode breakdown
- `/log4om/qsos` — Recent QSOs with filtering
- `/log4om/dxcc` — DXCC entity list with modes worked
- `/log4om/contests` — Contest participation history

### Propagation Data

Core scrapes solar/propagation data from N0NBH:
- Solar flux, K-index, A-index, sunspot number
- Band conditions (day/night) for 160m through 6m
- 7-day history and 3-day forecast
- Data cached with 15-minute TTL

### POTA Integration

Core fetches from the POTA API (api.pota.app):
- `/pota/spots` — Current activator spots (2 min cache)
- `/pota/park/{ref}` — Park details (1 hour cache)
- `/pota/parks/nearby` — Parks near home grid (24 hour cache)
- `/pota/plan/{ref}` — Full activation plan with band recommendations
- Park references use country prefix: US-1228 (not K-prefix)
- Nearby parks fetched via `/location/parks/US-CO` endpoint

### Contest System

Core provides contest calendar and live dashboard:
- Major contests hardcoded with recurring date patterns
- WA7BNM calendar scraped weekly for supplementary events
- Live dashboard computes rates, multipliers, score from Log4OM data
- Band recommendations combine propagation + contest band usage

## Configuration

### Core (.env)

```
POTA_HOME_GRID=DN70
POTA_HOME_STATE=US-CO
WORKER_BASE_URL=http://192.168.1.226:8101
```

### Worker (.env)

```
DX_CLUSTER_HOST=dxc.nc7j.com
DX_CLUSTER_PORT=7373
DX_CLUSTER_CALLSIGN=W0ABE
LOG4OM_DB_PATH=C:/Users/.../Log4OM/DB/log.db
```

## Quick Reference

```bash
# Check propagation
make prop

# View DX spots
make spots

# POTA spots
make pota

# DXCC progress
make dxcc

# Run full radio test
make test-radio
```
