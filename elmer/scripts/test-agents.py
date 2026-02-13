#!/usr/bin/env python3
"""End-to-end agent system test.

Tests the full agent lifecycle: registry, API, triggers, execution,
and orchestrator. Requires elmer-core to be running.
"""

import json
import sys
import time

import httpx

CORE_URL = "http://localhost:8100"
TIMEOUT = 30.0

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
        msg += f" — {detail}"
    print(msg)


def get(path: str, **kwargs) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
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


def test_core_health() -> bool:
    print("\n1. Core Health")
    r = get("/health")
    if r and r.status_code == 200:
        ok("Core is healthy")
        return True
    fail("Core health check")
    return False


def test_agent_registry() -> None:
    print("\n2. Agent Registry")
    r = get("/agents")
    if not r or r.status_code != 200:
        fail("List agents")
        return
    agents = r.json()
    ok(f"Listed {len(agents)} agents")

    expected = {
        "daily-briefing", "weekly-digest", "node-watchdog",
        "allstar-monitor", "home-assistant-reactor", "meshtastic-responder",
    }
    names = {a["name"] for a in agents}
    missing = expected - names
    if missing:
        fail(f"Missing agents: {missing}")
    else:
        ok("All expected agents registered")


def test_agent_detail() -> None:
    print("\n3. Agent Detail")
    r = get("/agents/daily-briefing")
    if not r or r.status_code != 200:
        fail("Get agent detail")
        return
    agent = r.json()
    if agent.get("name") == "daily-briefing":
        ok("Agent detail returned")
    else:
        fail("Agent detail name mismatch")

    if agent.get("triggers"):
        ok(f"Agent has {len(agent['triggers'])} triggers")
    else:
        fail("Agent has no triggers")

    if agent.get("tools"):
        ok(f"Agent has {len(agent['tools'])} tools")
    else:
        fail("Agent has no tools")


def test_orchestrator_status() -> None:
    print("\n4. Orchestrator Status")
    r = get("/agents/orchestrator/status")
    if not r or r.status_code != 200:
        fail("Orchestrator status")
        return
    status = r.json()
    if status.get("running"):
        ok("Orchestrator running")
    else:
        fail("Orchestrator not running")

    if status.get("agents_registered", 0) > 0:
        ok(f"{status['agents_registered']} agents registered")
    else:
        fail("No agents registered in orchestrator")


def test_schedule() -> None:
    print("\n5. Schedule")
    r = get("/agents/schedule")
    if not r or r.status_code != 200:
        fail("Get schedule")
        return
    jobs = r.json()
    if jobs:
        ok(f"{len(jobs)} scheduled jobs")
    else:
        fail("No scheduled jobs found")


def test_manual_trigger() -> None:
    print("\n6. Manual Trigger")
    r = post("/agents/node-watchdog/run")
    if not r or r.status_code != 200:
        fail("Trigger node-watchdog")
        return
    result = r.json()
    run_id = result.get("id")
    if run_id:
        ok(f"Triggered node-watchdog (run #{run_id})")
    else:
        fail("No run ID returned")

    # Wait for completion.
    print("     Waiting for run to complete...")
    for _ in range(30):
        time.sleep(1)
        rr = get(f"/agents/node-watchdog/runs", params={"limit": 1})
        if rr and rr.status_code == 200:
            runs = rr.json()
            if runs and runs[0].get("id") == run_id:
                status = runs[0].get("status")
                if status in ("completed", "failed"):
                    if status == "completed":
                        ok(f"Run #{run_id} completed ({runs[0].get('duration_seconds', '?')}s)")
                    else:
                        fail(f"Run #{run_id} failed")
                    return
    fail(f"Run #{run_id} did not complete within 30s")


def test_runs_list() -> None:
    print("\n7. Runs List")
    r = get("/agents/runs", params={"limit": 5})
    if not r or r.status_code != 200:
        fail("List all runs")
        return
    runs = r.json()
    ok(f"Listed {len(runs)} runs")


def test_enable_disable() -> None:
    print("\n8. Enable/Disable")
    # Disable.
    r = post("/agents/weekly-digest/disable")
    if r and r.status_code == 200:
        ok("Disabled weekly-digest")
    else:
        fail("Disable weekly-digest")
        return

    # Verify disabled.
    r = get("/agents/weekly-digest")
    if r and r.status_code == 200:
        agent = r.json()
        if not agent.get("enabled"):
            ok("Verified disabled")
        else:
            fail("Agent still enabled after disable")

    # Re-enable.
    r = post("/agents/weekly-digest/enable")
    if r and r.status_code == 200:
        ok("Re-enabled weekly-digest")
    else:
        fail("Re-enable weekly-digest")


def test_crud_lifecycle() -> None:
    print("\n9. CRUD Lifecycle")
    test_agent = {
        "name": "test-agent-tmp",
        "display_name": "Test Agent",
        "description": "Temporary agent for testing",
        "model": "llama3.1:8b",
        "system_prompt": "You are a test agent.",
        "tools": [],
        "triggers": [],
        "output_channels": ["log"],
        "enabled": False,
        "max_concurrent": 1,
        "timeout_seconds": 30,
    }

    # Create.
    r = post("/agents", json=test_agent)
    if not r or r.status_code not in (200, 201):
        fail("Create test agent", f"status={r.status_code if r else 'none'}")
        return
    ok("Created test-agent-tmp")

    # Read.
    r = get("/agents/test-agent-tmp")
    if r and r.status_code == 200:
        ok("Read test-agent-tmp")
    else:
        fail("Read test-agent-tmp")

    # Delete.
    r = delete("/agents/test-agent-tmp")
    if r and r.status_code == 200:
        ok("Deleted test-agent-tmp")
    else:
        fail("Delete test-agent-tmp", f"status={r.status_code if r else 'none'}")

    # Verify gone.
    r = get("/agents/test-agent-tmp")
    if r and r.status_code == 404:
        ok("Verified test-agent-tmp deleted")
    else:
        fail("test-agent-tmp still exists after delete")


def test_tools_list() -> None:
    print("\n10. Tools Registry")
    r = get("/agents/tools")
    if not r or r.status_code != 200:
        fail("List tools")
        return
    tools = r.json()
    if tools:
        ok(f"{len(tools)} tools available")
        names = {t.get("name") for t in tools}
        expected = {"search_knowledge", "query_database", "send_telegram", "run_script"}
        missing = expected - names
        if missing:
            fail(f"Missing tools: {missing}")
        else:
            ok("All expected tools present")
    else:
        fail("No tools returned")


def main() -> None:
    print("=" * 60)
    print("  Elmer Agent System — End-to-End Tests")
    print("=" * 60)

    if not test_core_health():
        print("\nCore is not reachable. Aborting.")
        sys.exit(1)

    test_agent_registry()
    test_agent_detail()
    test_orchestrator_status()
    test_schedule()
    test_manual_trigger()
    test_runs_list()
    test_enable_disable()
    test_crud_lifecycle()
    test_tools_list()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
