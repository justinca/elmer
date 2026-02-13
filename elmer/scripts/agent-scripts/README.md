# Agent Scripts

Scripts in this directory can be executed by agents using the `run_script` tool.

## Adding a New Script

1. Place the script in this directory
2. Make it executable: `chmod +x script-name.sh`
3. The script will be available to agents that have the `run_script` tool configured
4. No container rebuild needed — this directory is mounted as a Docker volume

## Constraints

- **Timeout**: Scripts are killed after 30 seconds
- **No interactive input**: Scripts must not require stdin
- **Output captured**: stdout and stderr are captured (max 10KB each)
- **Working directory**: Scripts run from this directory
- **Arguments**: Passed as positional parameters from the `args` field

## Existing Scripts

| Script | Description | Used By |
|---|---|---|
| `check-allstar.sh` | Check AllStar/Asterisk status on ShackPi via SSH | allstar-monitor |
| `check-weather.sh` | Query weewx weather data from WeatherPi via SSH | daily-briefing |
| `system-report.sh` | Gather health metrics from all Elmer nodes | daily-briefing, node-watchdog |
| `band-conditions.sh` | Fetch solar/band conditions from hamqth.com | daily-briefing |

## SSH Notes

Scripts that SSH to remote nodes (ShackPi, WeatherPi) require passwordless SSH
to be configured from the NUC. See `docs/manual/agent-scripts.md` for setup details.

All SSH commands should use these flags for Docker robustness:
```bash
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"
```
