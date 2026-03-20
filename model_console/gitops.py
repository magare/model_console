"""Git helper functions.

Provides branch creation, commit, diff capture, and revert operations
used by the engine to version-control each round's workspace changes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(workspace: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True
    )


def is_git_repo(workspace: Path) -> bool:
    proc = _run_git(workspace, ["rev-parse", "--is-inside-work-tree"])
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def current_branch(workspace: Path) -> str | None:
    proc = _run_git(workspace, ["branch", "--show-current"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def create_or_switch_branch(workspace: Path, branch_name: str) -> None:
    exists = _run_git(workspace, ["show-ref", "--verify", f"refs/heads/{branch_name}"])
    if exists.returncode == 0:
        checkout = _run_git(workspace, ["checkout", branch_name])
    else:
        checkout = _run_git(workspace, ["checkout", "-b", branch_name])
    if checkout.returncode != 0:
        raise RuntimeError(f"Failed to checkout branch {branch_name}: {checkout.stderr}")


def head_sha(workspace: Path) -> str | None:
    proc = _run_git(workspace, ["rev-parse", "HEAD"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def commit_all(workspace: Path, message: str) -> str | None:
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
    if not before or not after:
        proc = _run_git(workspace, ["diff"])
    else:
        proc = _run_git(workspace, ["diff", f"{before}..{after}"])
    if proc.returncode != 0:
        return ""
    return proc.stdout


def revert_commit(workspace: Path, commit_sha: str) -> str | None:
    proc = _run_git(workspace, ["revert", "--no-edit", commit_sha])
    if proc.returncode != 0:
        return None
    return head_sha(workspace)
