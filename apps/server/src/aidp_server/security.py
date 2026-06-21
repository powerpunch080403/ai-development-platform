import hashlib
import hmac
import secrets


def generate_pairing_code() -> str:
    digits = "".join(secrets.choice("0123456789") for _ in range(8))
    return f"{digits[:4]}-{digits[4:]}"


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_secret(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), expected_hash)
