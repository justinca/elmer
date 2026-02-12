#!/usr/bin/env bash
set -euo pipefail

echo "=== Elmer Deploy ==="

echo "Pulling latest changes..."
git pull --ff-only

echo "Building containers..."
docker compose build

echo "Restarting services..."
docker compose up -d

echo "Waiting for services to start..."
sleep 5

echo "Running health check..."
bash scripts/health-check.sh

echo ""
echo "Deploy complete."
