#!/bin/bash
# Check AllStar/Asterisk service status on ShackPi
# Usage: check-allstar.sh [host]
# Returns service status and active connections

HOST="${1:-shackpi}"

echo "=== AllStar Node Status ==="
ssh "$HOST" "systemctl is-active asterisk 2>/dev/null && echo 'Asterisk: running' || echo 'Asterisk: not running'"
echo ""
echo "=== Active Connections ==="
ssh "$HOST" "asterisk -rx 'rpt showvars 1999' 2>/dev/null || echo 'Could not query AllStar node'"
