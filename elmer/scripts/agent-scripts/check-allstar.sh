#!/bin/bash
# Check AllStar/Asterisk service status on ShackPi
# Usage: check-allstar.sh [host]
# Returns service status and active connections

HOST="${1:-shackpi}"
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"

echo "=== AllStar Node Status ==="
ssh $SSH_OPTS "$HOST" "systemctl is-active asterisk 2>/dev/null && echo 'Asterisk: running' || echo 'Asterisk: not running'"
echo ""
echo "=== Active Connections ==="
ssh $SSH_OPTS "$HOST" "asterisk -rx 'rpt showvars 1999' 2>/dev/null || echo 'Could not query AllStar node'"
echo ""
echo "=== Uptime ==="
ssh $SSH_OPTS "$HOST" "uptime" 2>/dev/null || echo "Could not get uptime"
