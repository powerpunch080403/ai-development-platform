from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from aidp_server.cli import create_pairing_code
from aidp_server.db.models import Device, PairingCode, PairingPurpose, RuntimeSession
from aidp_server.identity import ensure_local_user, get_local_user
from aidp_server.security import hash_secret
from conftest import AppHarness


def issue_code(harness: AppHarness) -> str:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    return code


def pair(harness: AppHarness, code: str, name: str = "Web UI on Windows") -> dict[str, object]:
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": name, "device_type": "web_ui"},
    )
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def test_local_user_bootstrap_is_idempotent(app_harness: AppHarness) -> None:
    with app_harness.session_factory() as session:
        first = ensure_local_user(session)
        session.commit()
        second = ensure_local_user(session)

        assert first.id == second.id
        assert get_local_user(session) is not None
        assert first.display_name == "Local Owner"
        assert first.account_id is None
        assert first.account_link_status.value == "local_only"


def test_pairing_code_stores_only_hash(app_harness: AppHarness) -> None:
    code = issue_code(app_harness)
    with app_harness.session_factory() as session:
        stored = session.scalar(select(PairingCode))
        assert stored is not None
        assert stored.code_hash == hash_secret(code)
        assert code not in stored.code_hash
        assert stored.purpose is PairingPurpose.WEB_UI


def test_pair_creates_device_and_session_and_code_is_single_use(
    app_harness: AppHarness,
) -> None:
    code = issue_code(app_harness)
    auth = pair(app_harness, code)

    assert "token" not in auth
    assert app_harness.settings.session_cookie_name in app_harness.client.cookies
    with app_harness.session_factory() as session:
        device = session.scalar(select(Device))
        runtime_session = session.scalar(select(RuntimeSession))
        pairing_code = session.scalar(select(PairingCode))
        assert device is not None and device.device_type.value == "web_ui"
        assert runtime_session is not None
        assert runtime_session.token_hash not in app_harness.client.cookies.values()
        assert pairing_code is not None and pairing_code.used_at is not None

    second = app_harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Other", "device_type": "web_ui"},
    )
    assert second.status_code == 400


def test_expired_pairing_code_fails(app_harness: AppHarness) -> None:
    code = "1111-2222"
    with app_harness.session_factory() as session:
        session.add(
            PairingCode(
                code_hash=hash_secret(code),
                purpose=PairingPurpose.WEB_UI,
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )
        session.commit()

    response = app_harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Expired", "device_type": "web_ui"},
    )
    assert response.status_code == 400


def test_me_logout_and_authenticated_lists(app_harness: AppHarness) -> None:
    auth = pair(app_harness, issue_code(app_harness))

    me = app_harness.client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["display_name"] == "Local Owner"
    assert app_harness.client.get("/devices").status_code == 200
    assert app_harness.client.get("/sessions").status_code == 200

    logout = app_harness.client.post("/auth/logout")
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert app_harness.client.get("/auth/me").status_code == 401
    with app_harness.session_factory() as session:
        runtime_session = session.get(RuntimeSession, auth["session"]["id"])  # type: ignore[index]
        assert runtime_session is not None and runtime_session.revoked_at is not None


def test_session_revoke_deletes_current_cookie(app_harness: AppHarness) -> None:
    auth = pair(app_harness, issue_code(app_harness))
    session_id = auth["session"]["id"]  # type: ignore[index]

    response = app_harness.client.post(f"/sessions/{session_id}/revoke")
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert app_harness.client.get("/auth/me").status_code == 401


def test_device_revoke_revokes_all_device_sessions(app_harness: AppHarness) -> None:
    auth = pair(app_harness, issue_code(app_harness))
    device_id = auth["device"]["id"]  # type: ignore[index]
    with app_harness.session_factory() as session:
        existing = session.scalar(select(RuntimeSession))
        assert existing is not None
        sibling = RuntimeSession(
            device_id=existing.device_id,
            local_user_id=existing.local_user_id,
            token_hash=hash_secret("sibling-token"),
            last_seen_at=datetime.now(timezone.utc),
            idle_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            absolute_expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
        session.add(sibling)
        session.commit()
        sibling_id = sibling.id

    response = app_harness.client.post(f"/devices/{device_id}/revoke")
    assert response.status_code == 200
    with app_harness.session_factory() as session:
        device = session.get(Device, device_id)
        loaded_sibling = session.get(RuntimeSession, sibling_id)
        assert device is not None and device.revoked_at is not None
        assert loaded_sibling is not None and loaded_sibling.revoked_at is not None
