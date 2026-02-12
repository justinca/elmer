#!/usr/bin/env bash
# Symlink the root .env into each package directory for local development.
# Docker containers use env_file: .env in docker-compose.yml (the root .env).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found. Copy .env.example to .env first."
    exit 1
fi

PACKAGES=(core dashboard knowledge telegram-bot transcription worker)

for pkg in "${PACKAGES[@]}"; do
    TARGET="$ROOT/packages/$pkg/.env"
    if [ -L "$TARGET" ]; then
        echo "  $pkg — symlink already exists"
    elif [ -f "$TARGET" ]; then
        echo "  $pkg — replacing file with symlink"
        mv "$TARGET" "$TARGET.bak"
        ln -s "$ENV_FILE" "$TARGET"
    else
        echo "  $pkg — creating symlink"
        ln -s "$ENV_FILE" "$TARGET"
    fi
done

echo ""
echo "Done. All packages now share ~/elmer/.env"
