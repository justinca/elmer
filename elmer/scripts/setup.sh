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

# Create Python virtual environments for local development.
# Packages with pyproject.toml are installed as editable (-e) so that
# cross-package imports work properly.
for pkg in common core dashboard worker telegram-bot agents knowledge transcription; do
    pkg_dir="packages/$pkg"
    if [ ! -d "$pkg_dir/.venv" ]; then
        echo "Creating venv for $pkg..."
        python3 -m venv "$pkg_dir/.venv"
        "$pkg_dir/.venv/bin/pip" install --quiet --upgrade pip
    fi

    # Install requirements.txt dependencies.
    if [ -f "$pkg_dir/requirements.txt" ]; then
        "$pkg_dir/.venv/bin/pip" install --quiet -r "$pkg_dir/requirements.txt"
    fi

    # Install the package itself as editable if it has a pyproject.toml.
    if [ -f "$pkg_dir/pyproject.toml" ]; then
        # Install common into packages that depend on it.
        case "$pkg" in
            core|worker)
                "$pkg_dir/.venv/bin/pip" install --quiet -e packages/common/
                ;;
        esac
        "$pkg_dir/.venv/bin/pip" install --quiet -e "$pkg_dir/"
    fi
done

echo ""
echo "Setup complete. Run 'make up' to start services."
