import argparse
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aidp_server.auth import PAIRING_CODE_TTL
from aidp_server.db.models import PairingCode, PairingPurpose
from aidp_server.db.session import get_session_factory
from aidp_server.security import generate_pairing_code, hash_secret


def create_pairing_code(session: Session) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + PAIRING_CODE_TTL
    for _ in range(5):
        code = generate_pairing_code()
        session.add(
            PairingCode(
                code_hash=hash_secret(code),
                purpose=PairingPurpose.WEB_UI,
                expires_at=expires_at,
            )
        )
        try:
            session.commit()
            return code, expires_at
        except IntegrityError:
            session.rollback()
    raise RuntimeError("Could not generate a unique pairing code")


def issue_pairing_code() -> tuple[str, datetime]:
    with get_session_factory()() as session:
        return create_pairing_code(session)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aidp-server")
    command = parser.add_subparsers(dest="command", required=True)
    auth = command.add_parser("auth")
    auth_command = auth.add_subparsers(dest="auth_command", required=True)
    auth_command.add_parser("pairing-code")
    args = parser.parse_args()

    if args.command == "auth" and args.auth_command == "pairing-code":
        code, expires_at = issue_pairing_code()
        print(f"Pairing code: {code}")
        print("Purpose: web_ui")
        print(f"Expires at: {expires_at.isoformat()}")


if __name__ == "__main__":
    main()
