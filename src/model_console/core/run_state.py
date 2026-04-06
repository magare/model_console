"""Typed helpers for persisted loop run state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from ..observability.logging import utc_now_iso
from ..models import LoopConfig


class RunState(TypedDict):
    run_id: str
    loop_id: str
    task_file: str
    task_text: str
    started_at: str
    next_round_index: int
    last_round_failed: bool
    pending_fixes: list[dict[str, Any]]
    scores: list[float]
    history: list[dict[str, Any]]
    terminated: bool
    paused: bool
    latest_artifact_path: str
    git_enabled: bool
    git_initialized: bool
    git_branch: str
    task_mode: str
    workflow_path: str
    workflow_phase: str
    completed_steps: list[str]
    active_step_id: str
    no_progress_rounds: int
    termination_reason: str
    workflow_steps: dict[str, dict[str, Any]]
    integration_done: bool
    current_step_attempts: int


def build_initial_state(
    *,
    run_id: str,
    loop_cfg: LoopConfig,
    task_file: Path,
    task_text: str,
) -> RunState:
    started_at = utc_now_iso()
    return RunState(
        run_id=run_id,
        loop_id=loop_cfg.loop_id,
        task_file=str(task_file),
        task_text=task_text,
        started_at=started_at,
        next_round_index=0,
        last_round_failed=False,
        pending_fixes=[],
        scores=[],
        history=[],
        terminated=False,
        paused=False,
        latest_artifact_path="",
        git_enabled=False,
        git_initialized=False,
        git_branch="",
        task_mode="simple",
        workflow_path="",
        workflow_phase="plan",
        completed_steps=[],
        active_step_id="",
        no_progress_rounds=0,
        termination_reason="",
        workflow_steps={},
        integration_done=False,
        current_step_attempts=0,
    )


def with_state_defaults(
    state: dict[str, Any],
    *,
    run_id: str,
    loop_cfg: LoopConfig,
    task_file: Path,
) -> RunState:
    merged: dict[str, Any] = {
        **build_initial_state(
            run_id=run_id,
            loop_cfg=loop_cfg,
            task_file=task_file,
            task_text="",
        ),
        **state,
    }
    for key in ("pending_fixes", "scores", "history", "completed_steps"):
        if not isinstance(merged.get(key), list):
            merged[key] = []
    if not isinstance(merged.get("workflow_steps"), dict):
        merged["workflow_steps"] = {}
    if not isinstance(merged.get("task_text"), str):
        merged["task_text"] = ""
    return RunState(**merged)


def run_manifest_payload(
    *,
    run_id: str,
    loop_cfg: LoopConfig,
    task_file: Path,
    task_mode: str,
) -> dict[str, Any]:
    from dataclasses import asdict

    return {
        "run_id": run_id,
        "loop_id": loop_cfg.loop_id,
        "task_file": str(task_file),
        "task_mode": task_mode,
        "loop_config": asdict(loop_cfg),
    }
