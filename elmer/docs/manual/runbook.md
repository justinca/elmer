# Operations Runbook

## Starting the Stack

```bash
# Start all services
docker compose up -d

# Verify health
bash scripts/health-check.sh
```

## Stopping the Stack

```bash
docker compose down
```

## Health Checks

```bash
# Quick check
curl http://localhost:8100/health

# Full node status
curl http://localhost:8100/health/nodes

# Service catalog
curl http://localhost:8100/docs/services

# Regenerate documentation
curl http://localhost:8100/docs/generate
# or
bash scripts/generate-docs.sh
```

## Troubleshooting

### Core API Not Responding

1. Check container status: `docker compose ps elmer-core`
2. Check logs: `docker compose logs elmer-core --tail 50`
3. Verify port 8100 is not in use: `ss -tlnp | grep 8100`
4. Restart: `docker compose restart elmer-core`

### Worker Not Connecting

1. Verify worker is running on the Windows machine
2. Check MQTT heartbeats: `mosquitto_sub -t "elmer/worker/heartbeat" -C 1`
3. Verify network connectivity: `ping $ELMER_WORKER_HOST`
4. Check worker logs on the Windows machine

### Database Issues

1. Check container: `docker compose ps elmer-postgres`
2. Check logs: `docker compose logs elmer-postgres --tail 50`
3. Verify connectivity: `psql -h localhost -U postgres -d elmer -c "SELECT 1"`
4. Check disk space: `df -h`
5. Re-run schema init: `bash scripts/init-db.sh`

### MQTT Issues

1. Check broker: `docker compose ps elmer-mqtt`
2. Test publish: `mosquitto_pub -t "test" -m "hello"`
3. Test subscribe: `mosquitto_sub -t "elmer/#" -v -C 5`
4. Check logs: `docker compose logs elmer-mqtt --tail 50`

## Backup Procedures

### Database Backup

```bash
# Dump the elmer database
pg_dump -h localhost -U postgres elmer > backup_$(date +%Y%m%d).sql

# Restore
psql -h localhost -U postgres elmer < backup_YYYYMMDD.sql
```

### Configuration Backup

```bash
# Back up .env and docker-compose
cp .env .env.backup
cp docker-compose.yaml docker-compose.yaml.backup
```

## Log Locations

| Service | Log Command |
|---------|-------------|
| Core API | `docker compose logs elmer-core` |
| Dashboard | `docker compose logs elmer-dashboard` |
| PostgreSQL | `docker compose logs elmer-postgres` |
| MQTT | `docker compose logs elmer-mqtt` |
