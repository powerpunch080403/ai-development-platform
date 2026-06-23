from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aidp_server.auth import CurrentAuth
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import ApprovalMode

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsSummaryView(BaseModel):
    approval_mode: str
    available_approval_modes: list[str]
    allow_danger_local_config: bool
    active_grant_placeholder: str
    adapter_summary: str


@router.get("/summary", response_model=SettingsSummaryView)
def get_settings_summary(
    settings: Annotated[Settings, Depends(get_settings)],
    current: CurrentAuth,
) -> SettingsSummaryView:
    return SettingsSummaryView(
        approval_mode=ApprovalMode.ASK_FOR_APPROVAL.value,
        available_approval_modes=[m.value for m in ApprovalMode],
        allow_danger_local_config=settings.antigravity_cli_allow_dangerous_skip_permissions,
        active_grant_placeholder="[Placeholder: User-specific grant configuration not fully exposed yet]",
        adapter_summary=f"External CLI path: {settings.antigravity_cli_path if settings.enable_experimental_antigravity_cli else 'Disabled'}",
    )
