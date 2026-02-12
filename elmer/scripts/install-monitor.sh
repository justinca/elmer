#!/usr/bin/env bash
# ============================================================
# Elmer Pi Monitor — Installation Script
#
# Usage:
#   scp install-monitor.sh <monitor-script>.py <service-file>.service pi@<host>:~/
#   ssh pi@<host> 'bash install-monitor.sh <MQTT_HOST> [monitor-type]'
#
# Arguments:
#   $1  MQTT broker hostname/IP (required)
#   $2  Monitor type: "shackpi" or "weatherpi" (default: auto-detect from hostname)
#
# What it does:
#   1. Creates /opt/elmer-monitor/
#   2. Creates a Python venv with paho-mqtt + psutil
#   3. Copies the monitor script into place
#   4. Writes an .env file with MQTT_HOST
#   5. Installs the systemd service, enables, and starts it
# ============================================================

set -euo pipefail

MQTT_HOST="${1:?Usage: $0 <MQTT_HOST> [shackpi|weatherpi]}"
MONITOR_TYPE="${2:-}"

INSTALL_DIR="/opt/elmer-monitor"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Auto-detect monitor type from hostname if not provided.
# ---------------------------------------------------------------------------
if [[ -z "$MONITOR_TYPE" ]]; then
    HOSTNAME_LOWER="$(hostname | tr '[:upper:]' '[:lower:]')"
    if [[ "$HOSTNAME_LOWER" == *shack* ]]; then
        MONITOR_TYPE="shackpi"
    elif [[ "$HOSTNAME_LOWER" == *weather* ]]; then
        MONITOR_TYPE="weatherpi"
    else
        echo "ERROR: Cannot auto-detect monitor type from hostname '$(hostname)'."
        echo "       Please specify: $0 $MQTT_HOST [shackpi|weatherpi]"
        exit 1
    fi
fi

MONITOR_SCRIPT="${MONITOR_TYPE}-monitor.py"
SERVICE_NAME="elmer-${MONITOR_TYPE}-monitor"
SERVICE_FILE="${SERVICE_NAME}.service"

echo "=== Elmer ${MONITOR_TYPE} Monitor Installer ==="
echo "  MQTT_HOST:    ${MQTT_HOST}"
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Service:      ${SERVICE_NAME}"
echo ""

# ---------------------------------------------------------------------------
# Locate source files (look in current dir and script dir).
# ---------------------------------------------------------------------------
find_file() {
    local name="$1"
    if [[ -f "${SCRIPT_DIR}/${name}" ]]; then
        echo "${SCRIPT_DIR}/${name}"
    elif [[ -f "./${name}" ]]; then
        echo "./${name}"
    elif [[ -f "$HOME/${name}" ]]; then
        echo "$HOME/${name}"
    else
        echo ""
    fi
}

SRC_MONITOR="$(find_file "$MONITOR_SCRIPT")"
SRC_SERVICE="$(find_file "$SERVICE_FILE")"

if [[ -z "$SRC_MONITOR" ]]; then
    echo "ERROR: Cannot find ${MONITOR_SCRIPT}"
    echo "       Make sure it's in the same directory as this script."
    exit 1
fi

if [[ -z "$SRC_SERVICE" ]]; then
    echo "ERROR: Cannot find ${SERVICE_FILE}"
    echo "       Make sure it's in the same directory as this script."
    exit 1
fi

# ---------------------------------------------------------------------------
# Create install directory.
# ---------------------------------------------------------------------------
echo "[1/5] Creating ${INSTALL_DIR}..."
sudo mkdir -p "${INSTALL_DIR}"
sudo chown "$(whoami):$(whoami)" "${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# Create Python venv and install minimal dependencies.
# ---------------------------------------------------------------------------
echo "[2/5] Setting up Python virtual environment..."
if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi

"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet paho-mqtt psutil

# ---------------------------------------------------------------------------
# Copy monitor script.
# ---------------------------------------------------------------------------
echo "[3/5] Installing monitor script..."
cp "${SRC_MONITOR}" "${INSTALL_DIR}/${MONITOR_SCRIPT}"
chmod +x "${INSTALL_DIR}/${MONITOR_SCRIPT}"

# ---------------------------------------------------------------------------
# Write .env file.
# ---------------------------------------------------------------------------
echo "[4/5] Writing environment config..."
cat > "${INSTALL_DIR}/.env" <<EOF
MQTT_HOST=${MQTT_HOST}
MQTT_PORT=1883
ELMER_NODE_NAME=${MONITOR_TYPE}
HEARTBEAT_INTERVAL=30
EOF

echo "  Written: ${INSTALL_DIR}/.env"

# ---------------------------------------------------------------------------
# Install and start systemd service.
# ---------------------------------------------------------------------------
echo "[5/5] Installing systemd service..."
sudo cp "${SRC_SERVICE}" "/etc/systemd/system/${SERVICE_FILE}"

# Update User in service file to match current user.
CURRENT_USER="$(whoami)"
sudo sed -i "s/^User=.*/User=${CURRENT_USER}/" "/etc/systemd/system/${SERVICE_FILE}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Service status:"
sudo systemctl status "${SERVICE_NAME}" --no-pager -l || true
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
