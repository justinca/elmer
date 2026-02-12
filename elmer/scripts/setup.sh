#!/usr/bin/env bash
set -euo pipefail

echo "=== Elmer Setup ==="

# Check for .env
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Edit .env with your configuration before starting services."
else
    echo ".env already exists, skipping."
fi

# Create Python virtual environments for local development
for pkg in core dashboard worker telegram-bot agents knowledge transcription common; do
    pkg_dir="packages/$pkg"
    if [ -f "$pkg_dir/requirements.txt" ] && [ ! -d "$pkg_dir/.venv" ]; then
        echo "Creating venv for $pkg..."
        python3 -m venv "$pkg_dir/.venv"
        "$pkg_dir/.venv/bin/pip" install --quiet --upgrade pip
        "$pkg_dir/.venv/bin/pip" install --quiet -r "$pkg_dir/requirements.txt"
    fi
done

echo ""
echo "Setup complete. Run 'make up' to start services."
