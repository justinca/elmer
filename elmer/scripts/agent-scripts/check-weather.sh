#!/bin/bash
# Check weather station data from WeatherPi (weewx)
# Usage: check-weather.sh [host]
# Returns current conditions and recent observations

HOST="${1:-weatherpi}"
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no"

echo "=== weewx Service Status ==="
ssh $SSH_OPTS "$HOST" "systemctl is-active weewx 2>/dev/null && echo 'weewx: running' || echo 'weewx: not running'"

echo ""
echo "=== Recent Observations (last 5) ==="
ssh $SSH_OPTS "$HOST" "sqlite3 -header -column /var/lib/weewx/weewx.sdb \
  'SELECT datetime(dateTime, \"unixepoch\", \"localtime\") AS time, \
   printf(\"%.1f\", outTemp) AS temp_F, \
   printf(\"%.0f\", outHumidity) AS humidity, \
   printf(\"%.1f\", windSpeed) AS wind_mph, \
   printf(\"%.2f\", rain) AS rain_in, \
   printf(\"%.1f\", barometer) AS baro_inHg \
   FROM archive ORDER BY dateTime DESC LIMIT 5;'" 2>/dev/null || echo "WEATHER_UNAVAILABLE"

echo ""
echo "=== WeatherPi System ==="
ssh $SSH_OPTS "$HOST" "uptime; free -h | grep Mem" 2>/dev/null || echo "UNREACHABLE"
