#!/bin/bash
# Check AllStar/Asterisk service status on ShackPi
# Usage: check-allstar.sh [host]
# Returns service status and active connections

HOST="${1:-shackpi}"
SSH_OPTS="-F /dev/null -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

echo "=== AllStar Node Status ==="
ssh $SSH_OPTS "justin@$HOST" "systemctl is-active asterisk 2>/dev/null && echo 'Asterisk: running' || echo 'Asterisk: not running'"
echo ""
echo "=== Active Connections ==="
ssh $SSH_OPTS "justin@$HOST" "sudo /usr/sbin/asterisk -rx 'rpt show variables 68498' 2>/dev/null || echo 'Could not query AllStar node'"
echo ""
echo "=== Uptime ==="
ssh $SSH_OPTS "justin@$HOST" "uptime" 2>/dev/null || echo "Could not get uptime"
