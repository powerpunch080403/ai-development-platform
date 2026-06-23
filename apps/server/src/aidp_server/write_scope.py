import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

DEFAULT_WRITE_SCOPE: dict[str, Any] = {
    "mode": "paths",
    "paths": ["."],
    "allow_new_files": False,
    "allow_protected_paths": False,
}


@dataclass(frozen=True)
class ChangedPath:
    path: str
    status: str
    is_new_file: bool


class WriteScopeError(ValueError):
    code = "WRITE_SCOPE_INVALID"

    def __init__(self, message: str, *, paths: list[str] | None = None) -> None:
        super().__init__(message)
        self.paths = paths or []

    def detail(self) -> dict[str, object]:
        detail: dict[str, object] = {"code": self.code, "message": str(self)}
        if self.paths:
            detail["paths"] = self.paths
        return detail


class WriteScopeViolation(WriteScopeError):
    code = "WRITE_SCOPE_VIOLATION"


def _normalize_path(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    if not value:
        raise WriteScopeError("write_scope paths cannot contain empty values")
    if value == ".":
        return value
    if value.startswith("/") or re.match(r"^[A-Za-z]:($|/)", value):
        raise WriteScopeError(f"write_scope path must be relative: {raw_path}")
    trailing_slash = value.endswith("/")
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise WriteScopeError(f"write_scope path traversal is forbidden: {raw_path}")
    normalized = "/".join(part for part in parts if part not in ("", "."))
    if not normalized:
        raise WriteScopeError(f"write_scope path is invalid: {raw_path}")
    return f"{normalized}/" if trailing_slash else normalized


def normalize_write_scope(raw: Mapping[str, object] | None) -> dict[str, Any]:
    if raw is None:
        return {
            "mode": DEFAULT_WRITE_SCOPE["mode"],
            "paths": list(DEFAULT_WRITE_SCOPE["paths"]),
            "allow_new_files": DEFAULT_WRITE_SCOPE["allow_new_files"],
            "allow_protected_paths": DEFAULT_WRITE_SCOPE["allow_protected_paths"],
        }
    if raw.get("mode") != "paths":
        raise WriteScopeError('write_scope mode must be "paths"')
    paths = raw.get("paths")
    if not isinstance(paths, list) or not paths:
        raise WriteScopeError("write_scope paths must be a non-empty list")
    normalized_paths: list[str] = []
    for path in paths:
        if not isinstance(path, str):
            raise WriteScopeError("write_scope paths must contain only strings")
        normalized = _normalize_path(path)
        if normalized not in normalized_paths:
            normalized_paths.append(normalized)
    allow_new_files = raw.get("allow_new_files", False)
    if not isinstance(allow_new_files, bool):
        raise WriteScopeError("write_scope allow_new_files must be a boolean")

    allow_protected_paths = raw.get("allow_protected_paths", False)
    if not isinstance(allow_protected_paths, bool):
        raise WriteScopeError("write_scope allow_protected_paths must be a boolean")

    return {
        "mode": "paths",
        "paths": normalized_paths,
        "allow_new_files": allow_new_files,
        "allow_protected_paths": allow_protected_paths,
    }


def _normalize_changed_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    parts = PurePosixPath(normalized).parts
    if not normalized or ".." in parts or normalized.startswith("/"):
        raise WriteScopeViolation("Git reported an unsafe changed path", paths=[path])
    return "/".join(parts)


def _is_sensitive_path(path: str) -> bool:
    parts = path.split("/")
    if not parts:
        return False
    filename = parts[-1]

    if filename == ".env" or filename.startswith(".env."):
        return True

    sensitive_dirs = {"secrets", "artifacts", "credentials", "runtime-data"}
    if any(part in sensitive_dirs for part in parts):
        return True

    if filename.endswith(".sqlite") or filename.endswith(".db") or filename.endswith(".key"):
        return True

    return False


def is_path_allowed(relative_path: str, scope: Mapping[str, object], *, is_new_file: bool) -> bool:
    path = _normalize_changed_path(relative_path)
    if _is_sensitive_path(path) and not scope.get("allow_protected_paths"):
        return False
    if is_new_file and scope.get("allow_new_files") is not True:
        return False
    for allowed_value in scope.get("paths", []) if isinstance(scope.get("paths", []), list) else []:
        if not isinstance(allowed_value, str):
            continue
        if allowed_value == ".":
            return True
        if allowed_value.endswith("/"):
            prefix = allowed_value.rstrip("/")
            if path == prefix or path.startswith(f"{prefix}/"):
                return True
        elif path == allowed_value:
            return True
    return False


def validate_changed_paths(
    changed_paths: list[ChangedPath], raw_scope: Mapping[str, object] | None
) -> dict[str, Any]:
    scope = normalize_write_scope(raw_scope)
    denied = [
        change.path
        for change in changed_paths
        if not is_path_allowed(change.path, scope, is_new_file=change.is_new_file)
    ]
    if denied:
        raise WriteScopeViolation("Changed paths are outside the task write_scope", paths=denied)
    return scope


def parse_porcelain_v1_z(output: str) -> list[ChangedPath]:
    entries = output.split("\0")
    changed: list[ChangedPath] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4 or entry[2] != " ":
            raise WriteScopeViolation("Git returned an unrecognized status entry")
        status = entry[:2]
        path = entry[3:]
        changed.append(
            ChangedPath(path=path, status=status, is_new_file=status == "??" or "A" in status)
        )
        if "R" in status or "C" in status:
            if index >= len(entries) or not entries[index]:
                raise WriteScopeViolation("Git rename/copy status is incomplete")
            source_path = entries[index]
            index += 1
            changed.append(ChangedPath(path=source_path, status=status, is_new_file=False))
    return changed
