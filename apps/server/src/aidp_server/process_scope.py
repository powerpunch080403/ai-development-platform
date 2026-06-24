from pathlib import Path
from sqlalchemy.orm import Session

from aidp_server.db.models import ProjectRepository, GitWorktree


class ScopeValidationError(Exception):
    pass


def validate_scope(
    session: Session,
    working_directory: str,
    repository_id: str | None = None,
    worktree_id: str | None = None,
) -> None:
    # Resolve the requested working directory
    try:
        wd_path = Path(working_directory).resolve(strict=False)
    except Exception:
        raise ScopeValidationError("Invalid working directory format")

    allowed_paths = []

    if repository_id:
        repo = session.get(ProjectRepository, repository_id)
        if repo and repo.repository_path:
            allowed_paths.append(Path(repo.repository_path).resolve(strict=False))

    if worktree_id:
        worktree = session.get(GitWorktree, worktree_id)
        if worktree and worktree.worktree_path:
            # We don't resolve against the absolute system root if worktree_path is relative to app data,
            # but in this MVP worktree_path is typically absolute or relative to run dir.
            # We just resolve it.
            allowed_paths.append(Path(worktree.worktree_path).resolve(strict=False))

    if not allowed_paths:
        raise ScopeValidationError("No allowed scopes found for execution")

    for allowed in allowed_paths:
        if wd_path.is_relative_to(allowed):
            return

    raise ScopeValidationError("Working directory is outside allowed repository/worktree scope")
