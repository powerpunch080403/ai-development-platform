import pytest
from pydantic import ValidationError

from aidp_server.external_cli_adapters import ExternalCliRunExperimentalRequest
from aidp_server.config import Settings
from aidp_server.action_policy import ACTION_CATALOG

def test_external_cli_request_schema_is_strictly_controlled():
    # 1. Check supported modes
    for mode in ["controlled_readme_test", "controlled_scope_violation_test", "controlled_timeout_test"]:
        req = ExternalCliRunExperimentalRequest(
            worker_id="test_worker_id",
            mode=mode
        )
        assert req.mode == mode

    # 2. Check unsupported mode fails
    with pytest.raises(ValidationError):
        ExternalCliRunExperimentalRequest(
            worker_id="test_worker_id",
            mode="unsupported_mode_xyz"
        )

    # 3. Check extra forbid (free-form prompt or arbitrary command fields are rejected)
    with pytest.raises(ValidationError):
        ExternalCliRunExperimentalRequest(
            worker_id="test_worker_id",
            mode="controlled_readme_test",
            prompt="Do whatever you want"
        )
        
    with pytest.raises(ValidationError):
        ExternalCliRunExperimentalRequest(
            worker_id="test_worker_id",
            mode="controlled_readme_test",
            executable="echo",
            args=["hello"]
        )

def test_agy_tool_action_is_registered():
    action_types = [a.action_type for a in ACTION_CATALOG]
    assert "external_cli.run_antigravity_experimental" in action_types

def test_danger_flag_is_false_by_default():
    settings = Settings()
    assert settings.antigravity_cli_allow_dangerous_skip_permissions is False
    assert settings.enable_experimental_antigravity_cli is False
