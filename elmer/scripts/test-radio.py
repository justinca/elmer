#!/usr/bin/env python3
"""End-to-end radio intelligence system test.

Tests propagation, DX cluster, Log4OM, POTA, and contest endpoints.
Requires elmer-core to be running with worker connected.
"""

import sys

import httpx

CORE_URL = "http://localhost:8100"
TIMEOUT = 15.0
LONG_TIMEOUT = 30.0

passed = 0
failed = 0


def ok(label: str) -> None:
    global passed
    passed += 1
    print(f"  \u2705 {label}")


def fail(label: str, detail: str = "") -> None:
    global failed
    failed += 1
    msg = f"  \u274c {label}"
    if detail:
        msg += f" \u2014 {detail}"
    print(msg)


def get(path: str, timeout: float = TIMEOUT, **kwargs) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=timeout) as c:
            return c.get(f"{CORE_URL}{path}", **kwargs)
    except httpx.RequestError as e:
        fail(f"GET {path}", str(e))
        return None


def post(path: str, **kwargs) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            return c.post(f"{CORE_URL}{path}", **kwargs)
    except httpx.RequestError as e:
        fail(f"POST {path}", str(e))
        return None


def delete(path: str) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            return c.delete(f"{CORE_URL}{path}")
    except httpx.RequestError as e:
        fail(f"DELETE {path}", str(e))
        return None


# ── Propagation ─────────────────────────────────────────────


def test_propagation() -> None:
    print("\n1. Propagation")

    r = get("/propagation")
    if not r or r.status_code != 200:
        fail("GET /propagation")
        return
    data = r.json()
    if data.get("solar_flux"):
        ok(f"Solar flux: {data['solar_flux']}")
    else:
        fail("No solar flux in propagation data")

    bands = data.get("bands", {})
    if bands:
        ok(f"Band conditions for {len(bands)} bands")
    else:
        fail("No band conditions")

    # Forecast.
    r = get("/propagation/forecast")
    if r and r.status_code == 200:
        fc = r.json()
        if isinstance(fc, list) and fc:
            ok(f"Forecast: {len(fc)} days")
        else:
            ok("Forecast endpoint OK (may be empty)")
    else:
        fail("GET /propagation/forecast")

    # History.
    r = get("/propagation/history")
    if r and r.status_code == 200:
        ok("Propagation history OK")
    else:
        fail("GET /propagation/history")


# ── DX Cluster ──────────────────────────────────────────────


def test_dx() -> None:
    print("\n2. DX Cluster")

    r = get("/dx/spots", params={"limit": 5})
    if not r or r.status_code != 200:
        fail("GET /dx/spots")
        return
    spots = r.json()
    if isinstance(spots, list):
        ok(f"DX spots: {len(spots)} returned")
    else:
        fail("DX spots not a list")

    # Summary.
    r = get("/dx/spots/summary")
    if r and r.status_code == 200:
        summary = r.json()
        ok(f"DX summary: {summary.get('total_spots', '?')} spots")
    else:
        fail("GET /dx/summary")

    # Needs list.
    r = get("/dx/needs")
    if r and r.status_code == 200:
        needs = r.json()
        ok(f"Needs list: {len(needs)} entries")
    else:
        fail("GET /dx/needs")

    # Needs CRUD: add, verify, delete.
    test_need = {"entity": "Test Island", "band": "20m", "mode": "CW", "priority": 5}
    r = post("/dx/needs", json=test_need)
    if r and r.status_code in (200, 201):
        need_data = r.json()
        need_id = need_data.get("id")
        ok(f"Added test need (id={need_id})")

        if need_id:
            r = delete(f"/dx/needs/{need_id}")
            if r and r.status_code == 200:
                ok("Deleted test need")
            else:
                fail("Delete test need")
    else:
        fail("Add test need")

    # Entity lookup.
    r = get("/dx/entities/JA1ABC")
    if r and r.status_code == 200:
        entity = r.json()
        if entity.get("entity_name"):
            ok(f"Entity lookup: {entity['entity_name']}")
        else:
            ok("Entity lookup returned (may be empty)")
    else:
        fail("GET /dx/entities/JA1ABC")


# ── Log4OM ──────────────────────────────────────────────────


def test_log() -> None:
    print("\n3. Log4OM")

    r = get("/log/stats")
    if not r or r.status_code != 200:
        fail("GET /log/stats")
        return
    stats = r.json()
    total = stats.get("total_qsos", 0)
    ok(f"Log stats: {total:,} QSOs")

    countries = stats.get("unique_countries", 0)
    ok(f"Countries: {countries}")

    # DXCC.
    r = get("/log/dxcc", timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        data = r.json()
        entities = data if isinstance(data, list) else data.get("entities", [])
        ok(f"DXCC: {len(entities)} entities worked")
    else:
        fail("GET /log/dxcc")

    # Contests.
    r = get("/log/contests")
    if r and r.status_code == 200:
        ok("Contest history OK")
    else:
        fail("GET /log/contests")


# ── POTA ────────────────────────────────────────────────────


def test_pota() -> None:
    print("\n4. POTA")

    # Spots.
    r = get("/pota/spots", timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        spots = r.json()
        ok(f"POTA spots: {len(spots)}")
    else:
        fail("GET /pota/spots")

    # Park info.
    r = get("/pota/park/US-1228", timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        park = r.json()
        ok(f"Park: {park.get('name', '?')}")
    else:
        fail("GET /pota/park/US-1228")

    # Nearby parks.
    r = get("/pota/parks/nearby", params={"grid": "DN70", "radius": 50},
            timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        parks = r.json()
        ok(f"Nearby parks: {len(parks)}")
    else:
        fail("GET /pota/parks/nearby")

    # Park search.
    r = get("/pota/parks/search", params={"state": "US-CO"},
            timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        parks = r.json()
        ok(f"Park search (US-CO): {len(parks)} parks")
    else:
        fail("GET /pota/parks/search")

    # Activation plan.
    r = get("/pota/plan/US-1228", timeout=LONG_TIMEOUT)
    if r and r.status_code == 200:
        plan = r.json()
        park = plan.get("park", {})
        ok(f"Activation plan: {park.get('name', '?')} ({plan.get('distance_miles', '?')} mi)")
    else:
        fail("GET /pota/plan/US-1228")


# ── Contests ────────────────────────────────────────────────


def test_contest() -> None:
    print("\n5. Contests")

    r = get("/contest/upcoming", params={"days": 60})
    if r and r.status_code == 200:
        contests = r.json()
        ok(f"Upcoming contests: {len(contests)}")
    else:
        fail("GET /contest/upcoming")

    r = get("/contest/history")
    if r and r.status_code == 200:
        ok("Contest history OK")
    else:
        fail("GET /contest/history")

    r = get("/contest/recommend-band", params={"current_band": "20m"})
    if r and r.status_code == 200:
        rec = r.json()
        ok(f"Band recommendation: {rec.get('suggested_band', '?')}")
    else:
        fail("GET /contest/recommend-band")


# ── Radio Agents ────────────────────────────────────────────


def test_radio_agents() -> None:
    print("\n6. Radio Agents")

    expected = {"dx-spotter", "pota-advisor", "contest-coach", "band-monitor"}
    r = get("/agents")
    if not r or r.status_code != 200:
        fail("GET /agents")
        return
    agents = r.json()
    names = {a["name"] for a in agents}
    missing = expected - names
    if missing:
        fail(f"Missing agents: {missing}")
    else:
        ok(f"All radio agents registered ({len(expected)})")

    # Check dx-spotter detail.
    r = get("/agents/dx-spotter")
    if r and r.status_code == 200:
        agent = r.json()
        ok(f"DX Spotter: enabled={agent.get('enabled')}")
    else:
        fail("GET /agents/dx-spotter")


# ── Main ────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print("  Elmer Radio Intelligence \u2014 End-to-End Tests")
    print("=" * 60)

    # Health check first.
    r = get("/health")
    if not r or r.status_code != 200:
        print("\nCore is not reachable at", CORE_URL)
        sys.exit(1)
    ok("Core is healthy")

    test_propagation()
    test_dx()
    test_log()
    test_pota()
    test_contest()
    test_radio_agents()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
