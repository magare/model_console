"""Git helper functions.

Provides branch creation, commit, diff capture, and revert operations
used by the engine to version-control each round's workspace changes.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

__all__ = [
    "is_git_repo",
    "current_branch",
    "create_or_switch_branch",
    "head_sha",
    "commit_all",
    "capture_diff",
    "revert_commit",
]

logger = logging.getLogger(__name__)


def _run_git(workspace: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given workspace directory."""
    return subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True
    )


def is_git_repo(workspace: Path) -> bool:
    """Check if the given path is inside a git repository."""
    proc = _run_git(workspace, ["rev-parse", "--is-inside-work-tree"])
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def current_branch(workspace: Path) -> str | None:
    """Return the current git branch name, or None if not in a repo or detached."""
    proc = _run_git(workspace, ["branch", "--show-current"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def create_or_switch_branch(workspace: Path, branch_name: str) -> None:
    """Create a new branch or switch to an existing one.

    Raises:
        RuntimeError: If the checkout fails.
    """
    exists = _run_git(workspace, ["show-ref", "--verify", f"refs/heads/{branch_name}"])
    if exists.returncode == 0:
        checkout = _run_git(workspace, ["checkout", branch_name])
    else:
        checkout = _run_git(workspace, ["checkout", "-b", branch_name])
    if checkout.returncode != 0:
        raise RuntimeError(f"Failed to checkout branch {branch_name}: {checkout.stderr}")


def head_sha(workspace: Path) -> str | None:
    """Return the current HEAD commit SHA, or None if not in a repo."""
    proc = _run_git(workspace, ["rev-parse", "HEAD"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def commit_all(workspace: Path, message: str) -> str | None:
    """Stage and commit all changes in the workspace.

    Returns:
        The new commit SHA, or None if there were no changes to commit.

    Raises:
        RuntimeError: If git status, add, or commit fails.
    """
    status = _run_git(workspace, ["status", "--porcelain"])
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr}")
    if not status.stdout.strip():
        return None

    add = _run_git(workspace, ["add", "-A"])
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr}")

    commit = _run_git(workspace, ["commit", "-m", message])
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr}")

    return head_sha(workspace)


def capture_diff(workspace: Path, before: str | None, after: str | None) -> str:
    """Generate a git diff between two commits.

    Args:
        workspace: Path to the git repository
        before: Starting commit SHA (or None for working tree vs last commit)
        after: Ending commit SHA (or None for working tree vs last commit)

    Returns:
        The diff output. Returns empty string if git fails, with error logged.

    Note:
        This function returns empty string on failure rather than raising,
        as diffs are typically used for display/reporting where failure
        is not critical. Errors are logged for debugging.
    """
    if not before or not after:
        proc = _run_git(workspace, ["diff"])
    else:
        proc = _run_git(workspace, ["diff", f"{before}..{after}"])
    if proc.returncode != 0:
        logger.debug(f"git diff failed (before={before}, after={after}): {proc.stderr}")
        return ""
    return proc.stdout


def revert_commit(workspace: Path, commit_sha: str) -> str:
    """Revert a commit and return the new HEAD SHA.

    Raises:
        RuntimeError: If the revert fails (e.g., due to conflicts).
    """
    proc = _run_git(workspace, ["revert", "--no-edit", commit_sha])
    if proc.returncode != 0:
        raise RuntimeError(
            f"Git revert failed for commit {commit_sha}: {proc.stderr}. "
            f"This may be due to conflicts or other git state issues."
        )
    new_sha = head_sha(workspace)
    logger.debug(f"Reverted commit {commit_sha}, new HEAD: {new_sha}")
    return new_sha
