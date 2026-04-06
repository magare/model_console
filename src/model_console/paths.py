"""Workspace-scoped path helpers."""

from __future__ import annotations

from pathlib import Path


def resolve_within_workspace(workspace: Path, raw_path: str, arg_name: str) -> Path:
    """Resolve a user path while preventing escapes outside the workspace."""
    workspace = workspace.expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (workspace / candidate).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError(
            f"{arg_name} must stay inside workspace `{workspace}`; got `{resolved}`"
        )
    return resolved
