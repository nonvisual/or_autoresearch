"""Shared test fixtures."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def make_git_repo():
    """Factory: a scratch git repo with identity configured and one commit on it."""

    def _make(repo: Path, branch: str = "main") -> Path:
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", branch], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"], check=True
        )
        return repo

    return _make
