#!/bin/bash
# Fetch current solar/band conditions from hamqth.com
# Returns XML with solar flux, A-index, K-index, and band conditions

echo "=== Solar Data ==="
curl -s "https://www.hamqth.com/solarxml.php" 2>&1

echo ""
echo "=== Band Conditions ==="
curl -s "https://www.hamqth.com/dxc_activity.php" 2>&1 | head -50
