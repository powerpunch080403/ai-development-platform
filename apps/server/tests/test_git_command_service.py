import pytest
from unittest.mock import patch, MagicMock
import subprocess

from aidp_server.git_commands import (
    SubprocessGitCommandService,
    GitCommandError,
    GitCommandTimeoutError,
)


@pytest.fixture
def service():
    return SubprocessGitCommandService()


def test_status_porcelain_clean(service):
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = service.status_porcelain("/fake/path")

        assert result == ""
        mock_run.assert_called_once_with(
            ["git", "-C", "/fake/path", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            timeout=10,
        )


def test_status_porcelain_dirty(service):
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M file.txt\n"
        mock_run.return_value = mock_result

        result = service.status_porcelain("/fake/path")

        assert result == " M file.txt\n"


def test_status_porcelain_timeout(service):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=10)):
        with pytest.raises(GitCommandTimeoutError, match="Git command timed out after 10s"):
            service.status_porcelain("/fake/path", timeout_seconds=10)


def test_status_porcelain_called_process_error(service):
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(
            returncode=128, cmd=["git"], stderr="fatal: not a git repository"
        ),
    ):
        with pytest.raises(
            GitCommandError,
            match="Git command failed with exit code 128: fatal: not a git repository",
        ):
            service.status_porcelain("/fake/path")


def test_status_porcelain_other_error(service):
    with patch("subprocess.run", side_effect=OSError("No such file or directory")):
        with pytest.raises(
            GitCommandError, match="Failed to execute git command: No such file or directory"
        ):
            service.status_porcelain("/fake/path")
