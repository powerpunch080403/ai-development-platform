from aidp_server.db import models  # noqa: F401
from aidp_server.db.base import Base


def test_identity_tables_are_registered_in_metadata() -> None:
    assert {"local_users", "devices", "sessions", "pairing_codes"}.issubset(Base.metadata.tables)


def test_only_hash_columns_exist_for_pairing_codes_and_sessions() -> None:
    sessions = Base.metadata.tables["sessions"]
    pairing_codes = Base.metadata.tables["pairing_codes"]

    assert "token_hash" in sessions.c
    assert "token" not in sessions.c
    assert "code_hash" in pairing_codes.c
    assert "code" not in pairing_codes.c
