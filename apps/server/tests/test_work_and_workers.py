from datetime import datetime, timedelta, timezone

from aidp_server.cli import create_pairing_code
from aidp_server.db.models import RecordStatus, TaskAttempt, WorkerRun
from conftest import AppHarness


def authenticate(h: AppHarness) -> None:
    with h.session_factory() as s:
        code, _ = create_pairing_code(s)
    assert (
        h.client.post(
            "/auth/pair", json={"code": code, "device_name": "Work tests", "device_type": "web_ui"}
        ).status_code
        == 200
    )


def project(h: AppHarness, name: str = "P") -> str:
    return str(h.client.post("/projects", json={"name": name}).json()["id"])


def work(h: AppHarness, pid: str, parent: str | None = None) -> dict[str, object]:
    r = h.client.post(
        f"/projects/{pid}/work-items",
        json={"parent_work_item_id": parent, "title": "Goal", "work_item_type": "goal"},
    )
    assert r.status_code == 201
    return r.json()  # type: ignore[no-any-return]


def task(h: AppHarness, pid: str, wid: str | None = None) -> dict[str, object]:
    r = h.client.post(
        f"/projects/{pid}/tasks",
        json={
            "work_item_id": wid,
            "title": "Do work",
            "instructions": "Record only",
            "risk_level": "R1",
            "requested_worker_kind": "manual",
        },
    )
    assert r.status_code == 201
    return r.json()  # type: ignore[no-any-return]


def worker(h: AppHarness, name: str) -> dict[str, object]:
    r = h.client.post(
        "/workers",
        json={"display_name": name, "worker_kind": "manual", "capabilities": {"manual": True}},
    )
    assert r.status_code == 201
    return r.json()  # type: ignore[no-any-return]


def test_work_task_worker_apis_require_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/workers").status_code == 401
    assert app_harness.client.get("/projects/x/tasks").status_code == 401


def test_work_item_tree_and_project_scope(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    p1 = project(app_harness, "One")
    p2 = project(app_harness, "Two")
    root = work(app_harness, p1)
    child = work(app_harness, p1, str(root["id"]))
    assert child["parent_work_item_id"] == root["id"]
    bad = app_harness.client.post(
        f"/projects/{p2}/work-items",
        json={"parent_work_item_id": root["id"], "title": "Bad", "work_item_type": "bug"},
    )
    assert bad.status_code == 400


def test_task_scope_status_and_attempt_numbers(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    pid = project(app_harness)
    wi = work(app_harness, pid)
    t = task(app_harness, pid, str(wi["id"]))
    tid = str(t["id"])
    assert t["status"] == "draft"
    changed = app_harness.client.post(f"/tasks/{tid}/status", json={"status": "queued"})
    assert changed.status_code == 200 and changed.json()["queued_at"]
    a1 = app_harness.client.post(f"/tasks/{tid}/attempts", json={})
    a2 = app_harness.client.post(f"/tasks/{tid}/attempts", json={})
    assert a1.json()["attempt_number"] == 1 and a2.json()["attempt_number"] == 2
    updated = app_harness.client.post(
        f"/task-attempts/{a1.json()['id']}/status",
        json={"status": "worker_failed", "result_summary": "baseline"},
    )
    assert updated.status_code == 200 and updated.json()["status"] == "worker_failed"
    other = project(app_harness, "Other")
    other_wi = work(app_harness, other)
    assert (
        app_harness.client.post(
            f"/projects/{pid}/tasks",
            json={
                "work_item_id": other_wi["id"],
                "title": "Bad",
                "instructions": "Bad",
                "risk_level": "R1",
            },
        ).status_code
        == 400
    )


def test_worker_heartbeat_claim_expiry_release_and_revoke(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    pid = project(app_harness)
    t = task(app_harness, pid)
    attempt = app_harness.client.post(f"/tasks/{t['id']}/attempts", json={}).json()
    w1 = worker(app_harness, "One")
    w2 = worker(app_harness, "Two")
    heartbeat = app_harness.client.post(f"/workers/{w1['id']}/heartbeat")
    assert heartbeat.status_code == 200 and heartbeat.json()["last_seen_at"]
    claimed = app_harness.client.post(
        f"/workers/{w1['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )
    assert claimed.status_code == 200 and claimed.json()["status"] == "running_worker"
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    with app_harness.session_factory() as s:
        a = s.get(TaskAttempt, attempt["id"])
        assert a is not None
        worker_run = WorkerRun(
            local_user_id=a.local_user_id,
            project_id=a.project_id,
            repository_id=a.repository_id,
            task_id=a.task_id,
            task_attempt_id=a.id,
            worker_id=str(w1["id"]),
            adapter_kind="manual",
            status=RecordStatus.RUNNING,
            started_at=old_time,
            last_heartbeat_at=old_time,
            lease_expires_at=old_time,
            heartbeat_source="test",
        )
        s.add(worker_run)
        s.commit()
        worker_run_id = worker_run.id

    second_heartbeat = app_harness.client.post(f"/workers/{w1['id']}/heartbeat")
    assert second_heartbeat.status_code == 200
    with app_harness.session_factory() as s:
        worker_run = s.get(WorkerRun, worker_run_id)
        assert worker_run is not None
        assert worker_run.last_heartbeat_at is not None
        assert worker_run.lease_expires_at is not None
        assert worker_run.heartbeat_source == "worker_heartbeat"
    assert (
        app_harness.client.post(
            f"/workers/{w2['id']}/claim", json={"task_attempt_id": attempt["id"]}
        ).status_code
        == 409
    )
    with app_harness.session_factory() as s:
        a = s.get(TaskAttempt, attempt["id"])
        assert a is not None
        a.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.commit()
    reclaimed = app_harness.client.post(
        f"/workers/{w2['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )
    assert reclaimed.status_code == 200 and reclaimed.json()["claimed_by_worker_id"] == w2["id"]
    assert (
        app_harness.client.post(
            f"/workers/{w1['id']}/release",
            json={"task_attempt_id": attempt["id"], "next_status": "worker_failed"},
        ).status_code
        == 409
    )
    released = app_harness.client.post(
        f"/workers/{w2['id']}/release",
        json={
            "task_attempt_id": attempt["id"],
            "next_status": "worker_failed",
            "result_summary": "released",
        },
    )
    assert released.status_code == 200 and released.json()["claimed_by_worker_id"] is None
    assert app_harness.client.post(f"/workers/{w2['id']}/revoke").status_code == 200
    assert app_harness.client.post(f"/workers/{w2['id']}/heartbeat").status_code == 409
    assert (
        app_harness.client.post(
            f"/workers/{w2['id']}/claim", json={"task_attempt_id": attempt["id"]}
        ).status_code
        == 409
    )
    events = app_harness.client.get("/audit-events").json()
    assert any(e["event_type"] == "worker.claimed_attempt" for e in events)
