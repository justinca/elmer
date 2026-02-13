#!/bin/bash
# System report — gather health metrics from all Elmer nodes
# Usage: system-report.sh
# Returns system status for NUC, ShackPi, WeatherPi, and Worker

SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"

echo "=== NUC (Core) ==="
echo "Uptime: $(uptime)"
echo "Disk: $(df -h / | tail -1)"
echo "Memory: $(free -h | grep Mem 2>/dev/null || echo 'N/A')"
echo "Core Health: $(curl -s --connect-timeout 3 http://localhost:8100/health 2>/dev/null || echo 'core API unreachable')"

echo ""
echo "=== ShackPi ==="
ssh $SSH_OPTS shackpi \
  "echo \"Uptime: \$(uptime)\"; echo \"Disk: \$(df -h / | tail -1)\"; echo \"Memory: \$(free -h | grep Mem)\"" \
  2>/dev/null || echo "ShackPi: UNREACHABLE"

echo ""
echo "=== WeatherPi ==="
ssh $SSH_OPTS weatherpi \
  "echo \"Uptime: \$(uptime)\"; echo \"Disk: \$(df -h / | tail -1)\"; echo \"Memory: \$(free -h | grep Mem)\"" \
  2>/dev/null || echo "WeatherPi: UNREACHABLE"

echo ""
echo "=== Windows Worker ==="
curl -s --connect-timeout 5 http://192.168.1.226:8101/health 2>/dev/null || echo "Worker: UNREACHABLE"
