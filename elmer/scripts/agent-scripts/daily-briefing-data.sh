#!/bin/bash
# Gather ALL daily briefing data in one shot.
# Output is kept compact to fit within the 4000-char tool result limit.

SSH_OPTS="-F /dev/null -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
API="http://localhost:8100"

# Helper: fetch URL using Python (curl not available in container)
fetch() {
  python3 -c "
import urllib.request, json, sys
try:
    r = urllib.request.urlopen('$1', timeout=5)
    data = r.read().decode()
    if len(sys.argv) > 1 and sys.argv[1] == '--compact':
        d = json.loads(data)
        keys = sys.argv[2].split(',') if len(sys.argv) > 2 else []
        if keys:
            d = {k: d[k] for k in keys if k in d}
        print(json.dumps(d, separators=(',', ':')))
    else:
        sys.stdout.write(data)
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" "$2" "$3" 2>/dev/null
}

# --- WEATHER & FORECAST (from Home Assistant) ---
echo "=== WEATHER ==="
python3 -c "
import urllib.request, json, os
url = os.environ.get('HA_URL','')
token = os.environ.get('HA_TOKEN','')
hdrs = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
try:
    # Current conditions
    req = urllib.request.Request(f'{url}/api/states/weather.forecast_home', headers=hdrs)
    r = urllib.request.urlopen(req, timeout=5)
    d = json.loads(r.read())
    a = d.get('attributes',{})
    print(f'Condition: {d[\"state\"]}')
    print(f'Temp: {a.get(\"temperature\")}F, Humidity: {a.get(\"humidity\")}%, Wind: {a.get(\"wind_speed\")} mph')
    print(f'Pressure: {a.get(\"pressure\")} {a.get(\"pressure_unit\",\"\")}')
    # Forecast high/low
    data = json.dumps({'entity_id':'weather.forecast_home','type':'daily'}).encode()
    req2 = urllib.request.Request(f'{url}/api/services/weather/get_forecasts?return_response',
        data=data, headers=hdrs)
    r2 = urllib.request.urlopen(req2, timeout=5)
    fc = json.loads(r2.read()).get('service_response',{}).get('weather.forecast_home',{}).get('forecast',[])
    if fc:
        print(f'Today: High {fc[0].get(\"temperature\")}F, Low {fc[0].get(\"templow\")}F, {fc[0].get(\"condition\")}')
    if len(fc)>1:
        print(f'Tomorrow: High {fc[1].get(\"temperature\")}F, Low {fc[1].get(\"templow\")}F, {fc[1].get(\"condition\")}')
except Exception as e:
    print(f'UNAVAILABLE: {e}')
" 2>&1

# --- CALENDAR (from Home Assistant) ---
echo ""
echo "=== CALENDAR (today) ==="
python3 -c "
import urllib.request, json, os
from datetime import datetime, timedelta
url = os.environ.get('HA_URL','')
token = os.environ.get('HA_TOKEN','')
now = datetime.now()
start = now.strftime('%Y-%m-%dT00:00:00')
end = (now + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
try:
    req = urllib.request.Request(
        f'{url}/api/calendars/calendar.family?start={start}&end={end}',
        headers={'Authorization': f'Bearer {os.environ.get(\"HA_TOKEN\",\"\")}'})
    r = urllib.request.urlopen(req, timeout=5)
    events = json.loads(r.read())
    if not events:
        print('No events today')
    for e in events[:5]:
        s = e.get('start',{})
        time = s.get('dateTime','')
        if time:
            from datetime import datetime as dt
            t = dt.fromisoformat(time).strftime('%I:%M %p')
            print(f'- {t}: {e.get(\"summary\",\"?\")}')
        else:
            print(f'- All day: {e.get(\"summary\",\"?\")}')
except Exception as e:
    print(f'UNAVAILABLE: {e}')
" 2>&1

# --- PROPAGATION ---
echo ""
echo "=== PROPAGATION ==="
fetch "$API/propagation" --compact solar_flux,sunspot_number,a_index,k_index,bands || echo "UNAVAILABLE"

# --- DX SPOTS ---
echo ""
echo "=== DX SPOTS ==="
fetch "$API/dx/spots/summary" --compact total_last_hour,bands,modes || echo "UNAVAILABLE"

# --- SYSTEM HEALTH (last) ---
echo ""
echo "=== SYSTEM HEALTH ==="
echo "NUC: Up $(awk '{d=int($1/86400);h=int(($1%86400)/3600);printf "%dd%dh",d,h}' /proc/uptime), Disk $(df -h /app 2>/dev/null | awk 'NR==2{print $5}' || echo '?'), Mem $(awk '/MemAvailable/{printf "%.0fMB free",$2/1024}' /proc/meminfo)"
echo "Core API: $(fetch "$API/health" --compact status,uptime_seconds 2>/dev/null || echo 'UNREACHABLE')"
echo "ShackPi: $(ssh $SSH_OPTS justin@shackpi 'echo "Up $(uptime -p 2>/dev/null||uptime|sed "s/.*up/Up/;s/,.*//"), Disk $(df -h /|awk "NR==2{print \$5}"), Asterisk $(systemctl is-active asterisk 2>/dev/null)"' 2>/dev/null || echo 'UNREACHABLE')"
echo "WeatherPi: $(ssh $SSH_OPTS justin@weatherpi 'echo "Up $(uptime -p 2>/dev/null||uptime|sed "s/.*up/Up/;s/,.*//"), Disk $(df -h /|awk "NR==2{print \$5}"), weewx $(systemctl is-active weewx 2>/dev/null)"' 2>/dev/null || echo 'UNREACHABLE')"
echo "Worker: $(fetch "http://192.168.1.226:8101/health" --compact status,uptime_seconds 2>/dev/null || echo 'UNREACHABLE')"
