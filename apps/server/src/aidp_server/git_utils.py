from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

GIT_TIMEOUT_SECONDS = 5
SOURCE_ROOT = Path(__file__).resolve().parents[4]
FORBIDDEN_SOURCE_PATHS = tuple(
    (SOURCE_ROOT / name).resolve() for name in ("runtime-data", "artifacts", "worktrees")
)


@dataclass(frozen=True)
class GitRepositoryStatus:
    is_git_repository: bool
    repository_root: str | None = None
    current_branch: str | None = None
    default_branch: str | None = None
    last_commit_sha: str | None = None
    is_dirty: bool | None = None
    porcelain: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _run_git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
        shell=False,
        env=environment,
    )


def run_git_write(path: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )


def inspect_git_repository(repository_path: str | Path) -> GitRepositoryStatus:
    try:
        candidate = Path(repository_path).expanduser().resolve()
    except OSError:
        return GitRepositoryStatus(
            False, error_code="invalid_path", error_message="Path could not be resolved"
        )
    if not candidate.exists():
        return GitRepositoryStatus(
            False, error_code="path_not_found", error_message="Path not found"
        )
    if not candidate.is_dir():
        return GitRepositoryStatus(
            False, error_code="not_directory", error_message="Path is not a directory"
        )
    if any(_is_within(candidate, forbidden) for forbidden in FORBIDDEN_SOURCE_PATHS):
        return GitRepositoryStatus(
            False,
            error_code="forbidden_path",
            error_message="Runtime, artifact, and worktree paths cannot be registered",
        )

    try:
        root_result = _run_git(candidate, "rev-parse", "--show-toplevel")
    except FileNotFoundError:
        return GitRepositoryStatus(
            False, error_code="git_unavailable", error_message="Git is unavailable"
        )
    except subprocess.TimeoutExpired:
        return GitRepositoryStatus(
            False, error_code="git_timeout", error_message="Git command timed out"
        )

    if root_result.returncode != 0 or not root_result.stdout.strip():
        return GitRepositoryStatus(
            False, error_code="not_git_repository", error_message="Path is not a Git repository"
        )

    root = Path(root_result.stdout.strip()).resolve()
    try:
        status_result = _run_git(root, "status", "--porcelain")
        branch_result = _run_git(root, "branch", "--show-current")
        head_result = _run_git(root, "rev-parse", "HEAD")
        remote_head_result = _run_git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    except subprocess.TimeoutExpired:
        return GitRepositoryStatus(
            True,
            repository_root=str(root),
            error_code="git_timeout",
            error_message="Git command timed out",
        )

    if status_result.returncode != 0:
        return GitRepositoryStatus(
            True,
            repository_root=str(root),
            error_code="git_status_failed",
            error_message="Could not read Git status",
        )

    current_branch = branch_result.stdout.strip() or None if branch_result.returncode == 0 else None
    last_commit_sha = head_result.stdout.strip() or None if head_result.returncode == 0 else None
    default_branch: str | None = None
    if remote_head_result.returncode == 0 and remote_head_result.stdout.strip():
        default_branch = remote_head_result.stdout.strip().removeprefix("origin/")
    else:
        try:
            for candidate_branch in ("main", "master"):
                branch_exists = _run_git(
                    root, "show-ref", "--verify", "--quiet", f"refs/heads/{candidate_branch}"
                )
                if branch_exists.returncode == 0:
                    default_branch = candidate_branch
                    break
        except subprocess.TimeoutExpired:
            return GitRepositoryStatus(
                True,
                repository_root=str(root),
                error_code="git_timeout",
                error_message="Git command timed out",
            )
        default_branch = default_branch or current_branch

    porcelain = status_result.stdout.rstrip()
    return GitRepositoryStatus(
        is_git_repository=True,
        repository_root=str(root),
        current_branch=current_branch,
        default_branch=default_branch,
        last_commit_sha=last_commit_sha,
        is_dirty=bool(porcelain),
        porcelain=porcelain,
    )
