from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from aidp_server.config import Settings, get_settings
from aidp_server.db.models import Device, DeviceType, LocalUser, PairingCode, PairingPurpose
from aidp_server.db.models import RuntimeSession
from aidp_server.db.session import get_session
from aidp_server.identity import ensure_local_user
from aidp_server.security import generate_session_token, hash_secret, verify_secret

PAIRING_CODE_TTL = timedelta(minutes=10)
SESSION_IDLE_TTL = timedelta(days=30)
SESSION_ABSOLUTE_TTL = timedelta(days=90)


class PairRequest(BaseModel):
    code: str = Field(min_length=8, max_length=32)
    device_name: str = Field(min_length=1, max_length=200)
    device_type: DeviceType


class UserView(BaseModel):
    id: str
    display_name: str
    account_id: str | None
    account_link_status: str


class DeviceView(BaseModel):
    id: str
    display_name: str
    device_type: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class SessionView(BaseModel):
    id: str
    device_id: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None


class AuthView(BaseModel):
    user: UserView
    device: DeviceView
    session: SessionView


class LogoutView(BaseModel):
    status: str = "ok"


@dataclass
class AuthContext:
    user: LocalUser
    device: Device
    runtime_session: RuntimeSession


router = APIRouter(prefix="/auth", tags=["auth"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _auth_view(context: AuthContext) -> AuthView:
    return AuthView(
        user=UserView(
            id=context.user.id,
            display_name=context.user.display_name,
            account_id=context.user.account_id,
            account_link_status=context.user.account_link_status.value,
        ),
        device=DeviceView(
            id=context.device.id,
            display_name=context.device.display_name,
            device_type=context.device.device_type.value,
            created_at=context.device.created_at,
            last_seen_at=context.device.last_seen_at,
            revoked_at=context.device.revoked_at,
        ),
        session=SessionView(
            id=context.runtime_session.id,
            device_id=context.runtime_session.device_id,
            created_at=context.runtime_session.created_at,
            last_seen_at=context.runtime_session.last_seen_at,
            idle_expires_at=context.runtime_session.idle_expires_at,
            absolute_expires_at=context.runtime_session.absolute_expires_at,
            revoked_at=context.runtime_session.revoked_at,
        ),
    )


def get_current_auth(
    http_request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    session_token = http_request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    runtime_session = session.scalar(
        select(RuntimeSession).where(RuntimeSession.token_hash == hash_secret(session_token))
    )
    now = datetime.now(timezone.utc)
    if (
        runtime_session is None
        or runtime_session.revoked_at is not None
        or _as_utc(runtime_session.idle_expires_at) <= now
        or _as_utc(runtime_session.absolute_expires_at) <= now
        or not verify_secret(session_token, runtime_session.token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    device = session.get(Device, runtime_session.device_id)
    user = session.get(LocalUser, runtime_session.local_user_id)
    if device is None or user is None or device.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    runtime_session.last_seen_at = now
    runtime_session.idle_expires_at = min(now + SESSION_IDLE_TTL, _as_utc(runtime_session.absolute_expires_at))
    device.last_seen_at = now
    session.commit()
    return AuthContext(user=user, device=device, runtime_session=runtime_session)


CurrentAuth = Annotated[AuthContext, Depends(get_current_auth)]


@router.post("/pair", response_model=AuthView)
def pair(
    request: PairRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthView:
    if request.device_type is not DeviceType.WEB_UI:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing code")

    code_hash = hash_secret(request.code.strip())
    pairing_code = session.scalar(
        select(PairingCode).where(
            PairingCode.code_hash == code_hash,
            PairingCode.purpose == PairingPurpose.WEB_UI,
        )
    )
    now = datetime.now(timezone.utc)
    if (
        pairing_code is None
        or pairing_code.used_at is not None
        or pairing_code.revoked_at is not None
        or _as_utc(pairing_code.expires_at) <= now
        or not verify_secret(request.code.strip(), pairing_code.code_hash)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing code")

    claimed = session.execute(
        update(PairingCode)
        .where(
            PairingCode.id == pairing_code.id,
            PairingCode.used_at.is_(None),
            PairingCode.revoked_at.is_(None),
            PairingCode.expires_at > now,
        )
        .values(used_at=now),
        execution_options={"synchronize_session": False},
    )
    if getattr(claimed, "rowcount", 0) != 1:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing code")

    local_user = ensure_local_user(session)
    device = Device(
        local_user_id=local_user.id,
        account_id=None,
        device_type=DeviceType.WEB_UI,
        display_name=request.device_name.strip(),
        last_seen_at=now,
    )
    session.add(device)
    session.flush()

    token = generate_session_token()
    runtime_session = RuntimeSession(
        device_id=device.id,
        local_user_id=local_user.id,
        account_id=None,
        token_hash=hash_secret(token),
        last_seen_at=now,
        idle_expires_at=now + SESSION_IDLE_TTL,
        absolute_expires_at=now + SESSION_ABSOLUTE_TTL,
    )
    session.add(runtime_session)
    session.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        max_age=int(SESSION_ABSOLUTE_TTL.total_seconds()),
    )
    return _auth_view(AuthContext(local_user, device, runtime_session))


@router.get("/me", response_model=AuthView)
def me(current: CurrentAuth) -> AuthView:
    return _auth_view(current)


@router.post("/logout", response_model=LogoutView)
def logout(
    response: Response,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LogoutView:
    current.runtime_session.revoked_at = datetime.now(timezone.utc)
    session.commit()
    response.delete_cookie(key=settings.session_cookie_name, path="/", samesite="lax")
    return LogoutView()
