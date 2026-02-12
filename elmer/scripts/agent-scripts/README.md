# Agent Scripts

Scripts in this directory can be executed by agents using the `run_script` tool.

## Adding a New Script

1. Place the script in this directory
2. Make it executable: `chmod +x script-name.sh`
3. The script will be available to agents that have the `run_script` tool configured

## Constraints

- **Timeout**: Scripts are killed after 30 seconds
- **No interactive input**: Scripts must not require stdin
- **Output captured**: stdout and stderr are captured (max 10KB each)
- **Working directory**: Scripts run from this directory
- **Arguments**: Passed as positional parameters from the `args` field

## Existing Scripts

- `check-allstar.sh` — Check AllStar node status on ShackPi via SSH
- `band-conditions.sh` — Fetch current solar/band conditions from hamqth.com
