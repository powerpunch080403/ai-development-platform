from aidp_server.cli import create_pairing_code
from aidp_server.db.models import ApprovalMode
from conftest import AppHarness


def authenticate(harness: AppHarness) -> None:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Test", "device_type": "web_ui"},
    )
    assert response.status_code == 200


def test_get_settings_summary(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    response = app_harness.client.get("/settings/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["approval_mode"] == ApprovalMode.ASK_FOR_APPROVAL.value
    assert isinstance(data["available_approval_modes"], list)
    assert ApprovalMode.ASK_FOR_APPROVAL.value in data["available_approval_modes"]
    assert "allow_danger_local_config" in data
    assert "active_grant_placeholder" in data
    assert "adapter_summary" in data
