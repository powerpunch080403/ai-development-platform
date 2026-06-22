import os

SENSITIVE_ENV_KEY_PARTS = [
    "TOKEN",
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "AUTH",
    "BEARER",
    "SESSION",
    "COOKIE",
    "CREDENTIAL",
    "KEY",
]

DEFAULT_ALLOWED_ENV_KEYS = [
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "LANG",
    "LC_ALL",
    "PYTHONIOENCODING",
]

def is_sensitive_env_key(key: str) -> bool:
    key_upper = key.upper()
    return any(part in key_upper for part in SENSITIVE_ENV_KEY_PARTS)

def build_process_environment(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = {}
    
    allowed_upper = {allowed.upper() for allowed in DEFAULT_ALLOWED_ENV_KEYS}
    
    # 1. Inherit only allowed keys from os.environ
    for k, v in os.environ.items():
        if k.upper() in allowed_upper:
            if not is_sensitive_env_key(k):
                env[k] = v
                
    # 2. Add extra_env if provided, applying the same rules
    if extra_env:
        for k, v in extra_env.items():
            if k.upper() in allowed_upper:
                if not is_sensitive_env_key(k):
                    env[k] = v
                    
    return env

def redact_environment_for_record(env: dict[str, str]) -> dict[str, str]:
    if not env:
        return {}
    
    redacted_env = {}
    for k, v in env.items():
        if is_sensitive_env_key(k):
            redacted_env[k] = "[REDACTED]"
        else:
            redacted_env[k] = v
    return redacted_env
