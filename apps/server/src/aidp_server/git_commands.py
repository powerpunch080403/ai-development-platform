import subprocess
from pathlib import Path
from typing import Protocol


class GitCommandError(RuntimeError):
    pass


class GitCommandTimeoutError(GitCommandError):
    pass


class GitCommandService(Protocol):
    def status_porcelain(
        self, repository_path: str | Path, *, timeout_seconds: int = 10
    ) -> str: ...


class SubprocessGitCommandService(GitCommandService):
    def status_porcelain(self, repository_path: str | Path, *, timeout_seconds: int = 10) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repository_path), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout_seconds,
            )
            return result.stdout
        except subprocess.TimeoutExpired as e:
            raise GitCommandTimeoutError(f"Git command timed out after {timeout_seconds}s") from e
        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"Git command failed with exit code {e.returncode}: {e.stderr}"
            ) from e
        except Exception as e:
            raise GitCommandError(f"Failed to execute git command: {e}") from e


def get_git_command_service() -> GitCommandService:
    return SubprocessGitCommandService()
