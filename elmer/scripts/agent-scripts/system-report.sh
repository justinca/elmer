#!/bin/bash
# System report — gather health metrics from all Elmer nodes
# Usage: system-report.sh
# Returns system status for NUC, ShackPi, WeatherPi, and Worker

SSH_OPTS="-F /dev/null -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

echo "=== NUC (Core) ==="
# Read from /proc since uptime/free may not exist in the container
echo "Uptime: $(cat /proc/uptime | awk '{d=int($1/86400); h=int(($1%86400)/3600); m=int(($1%3600)/60); printf "%dd %dh %dm\n",d,h,m}')"
echo "Disk: $(df -h /app 2>/dev/null | tail -1 || df -h / | tail -1)"
echo "Memory: $(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "Total: %.0fMB, Used: %.0fMB, Avail: %.0fMB\n", t/1024, (t-a)/1024, a/1024}' /proc/meminfo)"
echo "Core Health: $(curl -s --connect-timeout 3 http://localhost:8100/health 2>/dev/null || echo 'core API unreachable')"

echo ""
echo "=== ShackPi ==="
ssh $SSH_OPTS justin@shackpi \
  "echo \"Uptime: \$(uptime)\"; echo \"Disk: \$(df -h / | tail -1)\"; echo \"Memory: \$(free -h | grep Mem)\"" \
  2>/dev/null || echo "ShackPi: UNREACHABLE"

echo ""
echo "=== WeatherPi ==="
ssh $SSH_OPTS justin@weatherpi \
  "echo \"Uptime: \$(uptime)\"; echo \"Disk: \$(df -h / | tail -1)\"; echo \"Memory: \$(free -h | grep Mem)\"" \
  2>/dev/null || echo "WeatherPi: UNREACHABLE"

echo ""
echo "=== Windows Worker ==="
curl -s --connect-timeout 5 http://192.168.1.226:8101/health 2>/dev/null || echo "Worker: UNREACHABLE"
