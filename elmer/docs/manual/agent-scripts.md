# Agent Scripts

Agent scripts are shell scripts that agents can execute via the `run_script` tool. They provide agents with access to system-level operations like SSH to remote nodes, system metrics collection, and external service checks.

## How It Works

- Scripts live in `scripts/agent-scripts/` in the repository
- Docker mounts them at `/app/agent-scripts:ro` (read-only) in the core container
- The `run_script` tool executes scripts with path traversal protection
- Output (stdout + stderr) is captured and returned to the agent

## Constraints

| Constraint | Value |
|---|---|
| Timeout | 30 seconds (script is killed if exceeded) |
| Max stdout | 10 KB (truncated beyond this) |
| Max stderr | 10 KB (truncated beyond this) |
| Interactive input | Not supported (no stdin) |
| Working directory | `/app/agent-scripts/` inside the container |
| Arguments | Passed as positional params via `args` field |

## SSH Setup

Many agent scripts SSH to Raspberry Pi nodes (ShackPi, WeatherPi) for remote data collection. This requires passwordless SSH from the NUC to the Pis.

### Prerequisites

1. **SSH keys on the NUC** (already in place at `~/.ssh/id_rsa`):
   ```bash
   # If you need to generate new keys:
   ssh-keygen -t ed25519 -C "elmer-nuc"
   ```

2. **Copy public key to each Pi**:
   ```bash
   ssh-copy-id justin@shackpi      # 192.168.1.65
   ssh-copy-id justin@weatherpi    # 192.168.1.177
   ```

3. **Verify passwordless access**:
   ```bash
   ssh -o BatchMode=yes shackpi "echo ok"
   ssh -o BatchMode=yes weatherpi "echo ok"
   ```

4. **Add hostnames to `/etc/hosts`** (if not using DNS):
   ```
   192.168.1.65   shackpi
   192.168.1.177  weatherpi
   ```

### Docker Integration

The SSH keys are mounted into the core container via `docker-compose.yml`:

```yaml
volumes:
  - /home/justin/.ssh:/root/.ssh:ro
```

The container runs as root, so keys mount at `/root/.ssh`. The `:ro` flag ensures the container cannot modify your SSH keys.

To verify SSH works from inside the container:

```bash
docker exec elmer-core ssh -o BatchMode=yes -o ConnectTimeout=5 shackpi "echo ok"
```

### SSH Best Practices for Scripts

Always use these flags in agent scripts to prevent hanging:

```bash
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"
ssh $SSH_OPTS hostname "command"
```

- `ConnectTimeout=5`: Give up after 5 seconds if host unreachable
- `BatchMode=yes`: Never prompt for password (fail instead)
- `StrictHostKeyChecking=no`: Accept new host keys automatically (suitable for trusted LAN)

## Adding a New Script

1. Create the script in `scripts/agent-scripts/`:
   ```bash
   vi scripts/agent-scripts/my-script.sh
   ```

2. Make it executable:
   ```bash
   chmod +x scripts/agent-scripts/my-script.sh
   ```

3. **No rebuild needed** — the directory is mounted as a Docker volume, so new scripts are immediately available.

4. Test from inside the container:
   ```bash
   docker exec elmer-core /app/agent-scripts/my-script.sh
   ```

5. Reference in an agent YAML:
   ```yaml
   tools:
     - name: run_script
       description: Run my custom script
       config: {}
   ```

   The agent will call the tool with `{"script": "my-script.sh", "args": "optional args"}`.

## Security Considerations

- **Read-only mount**: Scripts directory is mounted `:ro` — agents cannot modify scripts
- **SSH keys read-only**: The `.ssh` mount is also `:ro`
- **Path traversal blocked**: The `run_script` tool resolves paths and validates they stay within the scripts directory
- **Executable bit required**: Only files with `chmod +x` can be executed
- **Argument sanitization**: Arguments are parsed via `shlex.split()` which handles shell escaping safely
- **No credentials in scripts**: Use environment variables for secrets, not hardcoded values
- **Container runs as root**: Be aware that scripts have root privileges inside the container

## Existing Scripts

| Script | Description | SSH Target |
|---|---|---|
| `check-allstar.sh` | Check AllStar/Asterisk status on ShackPi | shackpi |
| `check-weather.sh` | Query weewx weather data from WeatherPi | weatherpi |
| `system-report.sh` | Gather health metrics from all nodes | shackpi, weatherpi, worker |
| `band-conditions.sh` | Fetch solar/band conditions from hamqth.com | None (HTTP) |
