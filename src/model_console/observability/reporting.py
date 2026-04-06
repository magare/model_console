"""Loop report serialization helpers."""

from __future__ import annotations

from typing import Any

from ..models import Assignment, RoundResult
from ..core.run_state import RunState


def build_loop_report(state: RunState) -> dict[str, Any]:
    return {
        "run_id": state["run_id"],
        "loop_id": state["loop_id"],
        "rounds_executed": len(state["history"]),
        "scores": state["scores"],
        "terminated": state["terminated"],
        "paused": state["paused"],
        "termination_reason": state["termination_reason"],
        "task_mode": state["task_mode"],
        "history": state["history"],
        "git_branch": state["git_branch"],
        "workflow_path": state["workflow_path"],
        "active_step_id": state["active_step_id"],
        "completed_steps": state["completed_steps"],
    }


def format_summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Run Summary: {report['run_id']}",
        "",
        f"- Loop: `{report['loop_id']}`",
        f"- Rounds executed: `{report['rounds_executed']}`",
        f"- Scores: `{report['scores']}`",
        f"- Git branch: `{report.get('git_branch', '')}`",
        f"- Terminated: `{report.get('terminated', False)}`",
        f"- Paused: `{report.get('paused', False)}`",
        f"- Termination reason: `{report.get('termination_reason', '')}`",
        f"- Task mode: `{report.get('task_mode', 'simple')}`",
        "",
        "## Round History",
    ]
    for item in report["history"]:
        lines.append(
            f"- {item['round_id']}: score={item.get('score')} failure={item.get('failure')} terminated={item.get('terminated')}"
        )
    return "\n".join(lines) + "\n"


def round_commit_message(
    loop_id: str,
    round_id: str,
    assignment: Assignment,
    round_result: RoundResult,
) -> str:
    impl = ",".join(assignment.implementers)
    rev = ",".join(assignment.reviewers)
    return f"loop:{loop_id} round:{round_id} impl:{impl} rev:{rev} score:{round_result.score}"


def round_history_entry(round_result: RoundResult, commit_sha: str | None) -> dict[str, Any]:
    return {
        "round_id": round_result.round_id,
        "score": round_result.score,
        "failure": round_result.failure,
        "terminated": round_result.terminated,
        "rollback_applied": round_result.rollback_applied,
        "assignment": {
            "implementers": round_result.assignment.implementers,
            "reviewers": round_result.assignment.reviewers,
        },
        "eval_passed": round_result.eval_result.passed,
        "commit_sha": commit_sha,
    }
