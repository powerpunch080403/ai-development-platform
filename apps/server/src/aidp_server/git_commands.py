import subprocess
from typing import Protocol
from pathlib import Path

class GitCommandError(Exception):
    """Raised when a git command fails."""
    pass

class GitCommandTimeoutError(GitCommandError):
    """Raised when a git command times out."""
    pass

class GitCommandService(Protocol):
    def status_porcelain(self, repo_path: Path | str, timeout_seconds: float = 10.0) -> str:
        """Runs git status --porcelain and returns the output."""
        ...

class SubprocessGitCommandService:
    def status_porcelain(self, repo_path: Path | str, timeout_seconds: float = 10.0) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "status", "--porcelain"],
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
            raise GitCommandError(f"Git command failed with exit code {e.returncode}: {e.stderr}") from e
        except Exception as e:
            raise GitCommandError(f"Failed to execute git command: {e}") from e

def get_git_command_service() -> GitCommandService:
    return SubprocessGitCommandService()
