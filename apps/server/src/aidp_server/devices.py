from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.auth import CurrentAuth, DeviceView, SessionView
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import Device, RuntimeSession
from aidp_server.db.session import get_session


class RevokeView(BaseModel):
    status: str = "ok"


router = APIRouter(tags=["sessions and devices"])


def _device_view(device: Device) -> DeviceView:
    return DeviceView(
        id=device.id,
        display_name=device.display_name,
        device_type=device.device_type.value,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
    )


def _session_view(runtime_session: RuntimeSession) -> SessionView:
    return SessionView(
        id=runtime_session.id,
        device_id=runtime_session.device_id,
        created_at=runtime_session.created_at,
        last_seen_at=runtime_session.last_seen_at,
        idle_expires_at=runtime_session.idle_expires_at,
        absolute_expires_at=runtime_session.absolute_expires_at,
        revoked_at=runtime_session.revoked_at,
    )


@router.get("/devices", response_model=list[DeviceView])
def list_devices(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[DeviceView]:
    devices = session.scalars(
        select(Device)
        .where(Device.local_user_id == current.user.id)
        .order_by(Device.created_at.desc())
    )
    return [_device_view(device) for device in devices]


@router.get("/sessions", response_model=list[SessionView])
def list_sessions(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[SessionView]:
    runtime_sessions = session.scalars(
        select(RuntimeSession)
        .where(RuntimeSession.local_user_id == current.user.id)
        .order_by(RuntimeSession.created_at.desc())
    )
    return [_session_view(runtime_session) for runtime_session in runtime_sessions]


@router.post("/sessions/{session_id}/revoke", response_model=RevokeView)
def revoke_session(
    session_id: str,
    response: Response,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RevokeView:
    runtime_session = session.get(RuntimeSession, session_id)
    if runtime_session is None or runtime_session.local_user_id != current.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if runtime_session.revoked_at is None:
        runtime_session.revoked_at = datetime.now(timezone.utc)
        session.commit()
    if runtime_session.id == current.runtime_session.id:
        response.delete_cookie(key=settings.session_cookie_name, path="/", samesite="lax")
    return RevokeView()


@router.post("/devices/{device_id}/revoke", response_model=RevokeView)
def revoke_device(
    device_id: str,
    response: Response,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RevokeView:
    device = session.get(Device, device_id)
    if device is None or device.local_user_id != current.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    now = datetime.now(timezone.utc)
    if device.revoked_at is None:
        device.revoked_at = now
    runtime_sessions = session.scalars(
        select(RuntimeSession).where(
            RuntimeSession.device_id == device.id,
            RuntimeSession.revoked_at.is_(None),
        )
    )
    revoked_current = False
    for runtime_session in runtime_sessions:
        runtime_session.revoked_at = now
        revoked_current = revoked_current or runtime_session.id == current.runtime_session.id
    session.commit()
    if revoked_current:
        response.delete_cookie(key=settings.session_cookie_name, path="/", samesite="lax")
    return RevokeView()
