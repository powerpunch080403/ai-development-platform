import re

# Redact anything like token=... api_key=... Bearer ...
# Case insensitive, matching word boundaries for common secret keys.
REDACT_PATTERN = re.compile(
    r"(?i)(token|api_key|password|secret|bearer|session)\s*[:=]\s*([^\s]+)",
)
BEARER_PATTERN = re.compile(r"(?i)(bearer)\s+([a-zA-Z0-9_\-\.]+)")


def redact_text(text: str) -> str:
    if not text:
        return text
    # Redact key=value pairs
    redacted = REDACT_PATTERN.sub(r"\1=[REDACTED]", text)
    # Redact Bearer tokens
    redacted = BEARER_PATTERN.sub(r"\1 [REDACTED]", redacted)
    return redacted


def redact_env(env: dict[str, str]) -> dict[str, str]:
    if not env:
        return {}

    redacted_env = {}
    for k, v in env.items():
        k_upper = k.upper()
        if any(
            secret in k_upper
            for secret in ["TOKEN", "API_KEY", "SECRET", "PASSWORD", "AUTH", "BEARER", "SESSION"]
        ):
            redacted_env[k] = "[REDACTED]"
        else:
            redacted_env[k] = v
    return redacted_env


def redact_args(args: list[str]) -> list[str]:
    return [redact_text(arg) for arg in args]
