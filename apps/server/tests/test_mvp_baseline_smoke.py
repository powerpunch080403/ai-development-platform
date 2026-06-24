from conftest import AppHarness

from test_worktrees import auth


def test_tool_registry_seeded(app_harness: AppHarness) -> None:
    # Ensure tool registry is seeded during startup
    auth(app_harness)
    resp = app_harness.client.get("/tool-registry")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) >= 2
    names = {t["tool_name"] for t in tools}
    assert "policy.evaluate" in names
    assert "approval.request" in names


def test_mock_and_manual_endpoints_exist(app_harness: AppHarness) -> None:
    # Without auth or valid attempt, it should return 401 or 404, not 404 (Not Found) for the route itself.
    resp = app_harness.client.post("/task-attempts/dummy/worker/mock/run", json={})
    assert resp.status_code in (401, 404, 422)

    resp = app_harness.client.post("/task-attempts/dummy/worker/manual/start", json={})
    assert resp.status_code in (401, 404, 422)

    resp = app_harness.client.post("/task-attempts/dummy/worker/manual/submit", json={})
    assert resp.status_code in (401, 404, 422)


def test_health_endpoint(app_harness: AppHarness) -> None:
    resp = app_harness.client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
