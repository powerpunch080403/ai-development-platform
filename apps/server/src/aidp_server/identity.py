from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.db.models import AccountLinkStatus, LocalUser


def get_local_user(session: Session) -> LocalUser | None:
    return session.scalar(select(LocalUser).order_by(LocalUser.created_at).limit(1))


def ensure_local_user(session: Session) -> LocalUser:
    local_user = get_local_user(session)
    if local_user is not None:
        return local_user

    local_user = LocalUser(
        display_name="Local Owner",
        account_id=None,
        account_link_status=AccountLinkStatus.LOCAL_ONLY,
    )
    session.add(local_user)
    session.flush()
    return local_user
