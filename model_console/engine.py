from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .eval import run_eval_commands
from .executors import AgentExecutor
from .gitops import (
    capture_diff,
    commit_all,
    create_or_switch_branch,
    head_sha,
    is_git_repo,
    revert_commit,
)
from .logging_utils import append_jsonl, ensure_dir, utc_now_iso, write_json
from .models import AppConfig, Assignment, LoopConfig, RoundResult
from .prompts import load_template, render_template
from .role_assignment import AssignmentContext, RoleAssignmentEngine
from .validator import validate_with_schema


class LoopEngine:
    def __init__(
        self,
        app_cfg: AppConfig,
        loop_id: str,
        task_file: Path,
        run_id: str | None = None,
        resume: bool = False,
        event_handler: Callable[[dict], None] | None = None,
    ) -> None:
        if loop_id not in app_cfg.loops:
            raise ValueError(f"Unknown loop_id `{loop_id}`")
        if not task_file.exists() and not resume:
            raise FileNotFoundError(f"Task file not found: {task_file}")

        self.app_cfg = app_cfg
        self.loop_cfg: LoopConfig = app_cfg.loops[loop_id]
        self.task_file = task_file
        self.resume = resume
        self.run_id = run_id or _default_run_id(loop_id)
        self.event_handler = event_handler

        self.run_dir = app_cfg.run_root / self.run_id
        self.loop_dir = self.run_dir / f"loop_{loop_id}"
        self.rounds_dir = self.loop_dir / "rounds"
        self.checkpoints_dir = self.loop_dir / "checkpoints"
        self.reports_dir = self.run_dir / "reports"
        self.logs_dir = self.run_dir / "logs"
        self.state_file = self.run_dir / "state.json"
        self.events_log = self.logs_dir / "events.jsonl"
        self.commands_log = self.logs_dir / "commands.jsonl"

        self.executor = AgentExecutor(
            app_cfg, self.events_log, self.commands_log, event_handler=event_handler
        )
        self.role_engine = RoleAssignmentEngine(self.loop_cfg)

        ensure_dir(self.rounds_dir)
        ensure_dir(self.checkpoints_dir)
        ensure_dir(self.reports_dir)
        ensure_dir(self.logs_dir)

        self.impl_schema_path = app_cfg.schemas_dir / "implementer.output.schema.json"
        self.rev_schema_path = app_cfg.schemas_dir / "reviewer.output.schema.json"
        self.workflow_schema_path = app_cfg.schemas_dir / "complex.workflow.schema.json"

        self.impl_template = load_template(app_cfg.prompts_dir / "implementer.template.txt")
        self.rev_template = load_template(app_cfg.prompts_dir / "reviewer.template.txt")

    def run(self) -> dict[str, Any]:
        state = self._load_or_init_state()
        self._maybe_init_git(state)

        if state.get("terminated", False):
            return self._write_reports(state)

        if state.get("paused", False):
            state["paused"] = False
            state["termination_reason"] = ""
            self._save_state(state)

        invocation_round_limit = self._invocation_round_limit(state)

        append_jsonl(
            self.events_log,
            {
                "timestamp": utc_now_iso(),
                "event": "loop_started",
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "task_file": str(self.task_file),
                "invocation_round_limit": invocation_round_limit,
            },
        )
        self._emit(
            {
                "timestamp": utc_now_iso(),
                "event": "loop_started",
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "task_file": str(self.task_file),
                "invocation_round_limit": invocation_round_limit,
            }
        )

        while state["next_round_index"] < invocation_round_limit:
            if self._dependency_mode_active(state):
                selection = self._select_next_workflow_step(state)
                if selection["status"] == "complete":
                    state["termination_reason"] = "workflow_complete"
                    state["terminated"] = True
                    self._save_state(state)
                    break
                if selection["status"] == "deadlock":
                    self._pause_workflow(
                        state,
                        reason="workflow_deadlock",
                        round_id=f"r{state['next_round_index'] + 1:02d}",
                    )
                    break
                next_step_id = selection.get("step_id", "")
                if str(state.get("active_step_id", "")) != str(next_step_id):
                    state["current_step_attempts"] = 0
                state["active_step_id"] = next_step_id
                self._save_workflow_artifact(state)

            round_index = state["next_round_index"]
            round_id = f"r{round_index + 1:02d}"
            round_dir = self.rounds_dir / round_id
            ensure_dir(round_dir)

            swap_request = self._read_swap_override()
            assignment = self.role_engine.assign(
                AssignmentContext(
                    round_index=round_index,
                    last_round_failed=state["last_round_failed"],
                    requested_swap=swap_request,
                )
            )

            append_jsonl(
                self.events_log,
                {
                    "timestamp": utc_now_iso(),
                    "event": "roles_assigned",
                    "round_id": round_id,
                    "implementers": assignment.implementers,
                    "reviewers": assignment.reviewers,
                },
            )
            self._emit(
                {
                    "timestamp": utc_now_iso(),
                    "event": "roles_assigned",
                    "round_id": round_id,
                    "implementers": assignment.implementers,
                    "reviewers": assignment.reviewers,
                }
            )

            before_sha = head_sha(self.app_cfg.workspace_root) if state["git_enabled"] else None

            try:
                round_result = self._run_round(round_id, round_dir, assignment, state)
            except Exception as exc:  # pragma: no cover - defensive
                state["last_round_failed"] = True
                state["history"].append(
                    {
                        "round_id": round_id,
                        "status": "failed",
                        "error": str(exc),
                        "assignment": asdict(assignment),
                    }
                )
                append_jsonl(
                    self.events_log,
                    {
                        "timestamp": utc_now_iso(),
                        "event": "round_failed",
                        "round_id": round_id,
                        "error": str(exc),
                    },
                )
                self._emit(
                    {
                        "timestamp": utc_now_iso(),
                        "event": "round_failed",
                        "round_id": round_id,
                        "error": str(exc),
                    }
                )
                self._save_state(state)
                if self.loop_cfg.swap_on_failure:
                    state["next_round_index"] += 1
                    if self._dependency_mode_active(state):
                        state["no_progress_rounds"] = int(state.get("no_progress_rounds", 0)) + 1
                        state["current_step_attempts"] = int(
                            state.get("current_step_attempts", 0)
                        ) + 1
                        self._save_state(state)
                    continue
                raise

            commit_sha = None
            rollback_applied = False
            if state["git_enabled"]:
                commit_sha = commit_all(
                    self.app_cfg.workspace_root,
                    _round_commit_message(self.loop_cfg.loop_id, round_id, assignment, round_result),
                )
                after_sha = head_sha(self.app_cfg.workspace_root)
                diff = capture_diff(self.app_cfg.workspace_root, before_sha, after_sha)
                if diff:
                    (round_dir / "git.diff.patch").write_text(diff, encoding="utf-8")

                if round_result.failure and commit_sha:
                    reverted = revert_commit(self.app_cfg.workspace_root, commit_sha)
                    rollback_applied = reverted is not None
                    round_result.rollback_applied = rollback_applied

            if self._dependency_mode_active(state):
                self._update_workflow_after_round(state, round_result, round_dir)
                round_result.terminated = bool(
                    round_result.terminated and self._workflow_completion_ready(state)
                )

            state["history"].append(_round_history_entry(round_result, commit_sha))
            state["last_round_failed"] = round_result.failure
            state["pending_fixes"] = round_result.merged_review.get("prioritized_fixes", [])
            state["scores"].append(round_result.score)
            state["next_round_index"] += 1
            state["latest_artifact_path"] = round_result.implementer_output.get("artifact", {}).get(
                "path", ""
            )
            self._save_state(state)

            if round_result.terminated:
                state["terminated"] = True
                state["termination_reason"] = "accepted"
                self._save_state(state)
                break

            if self._dependency_mode_active(state):
                if self._workflow_retry_exhausted(state):
                    self._pause_workflow(
                        state,
                        reason="workflow_step_retry_exhausted",
                        round_id=round_id,
                    )
                    break
                if self._workflow_stagnated(state):
                    self._pause_workflow(
                        state,
                        reason="workflow_stagnation",
                        round_id=round_id,
                    )
                    break
                continue

            if self._stagnated(state["scores"]):
                state["terminated"] = True
                state["termination_reason"] = "score_stagnation"
                append_jsonl(
                    self.events_log,
                    {
                        "timestamp": utc_now_iso(),
                        "event": "terminated_stagnation",
                        "round_id": round_id,
                        "scores": state["scores"],
                    },
                )
                self._emit(
                    {
                        "timestamp": utc_now_iso(),
                        "event": "terminated_stagnation",
                        "round_id": round_id,
                        "scores": state["scores"],
                    }
                )
                self._save_state(state)
                break

        if (
            not state.get("terminated", False)
            and not state.get("paused", False)
            and state["next_round_index"] >= invocation_round_limit
        ):
            if self._dependency_mode_active(state) and not self._workflow_completion_ready(state):
                state["paused"] = True
                state["termination_reason"] = "max_rounds_incomplete"
            else:
                state["terminated"] = True
                state["termination_reason"] = "max_rounds_reached"
            self._save_state(state)

        report = self._write_reports(state)
        append_jsonl(
            self.events_log,
            {
                "timestamp": utc_now_iso(),
                "event": "loop_completed",
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "report": report,
            },
        )
        self._emit(
            {
                "timestamp": utc_now_iso(),
                "event": "loop_completed",
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "rounds_executed": len(state["history"]),
                "scores": state["scores"],
                "paused": state.get("paused", False),
                "termination_reason": state.get("termination_reason", ""),
            }
        )
        return report

    def _run_round(
        self,
        round_id: str,
        round_dir: Path,
        assignment: Assignment,
        state: dict[str, Any],
    ) -> RoundResult:
        task_text = self._get_task_text(state)
        current_artifact_snapshot = self._load_artifact_snapshot(state)
        prioritized_fixes = state.get("pending_fixes") or []
        workflow_context = self._workflow_context_for_prompt(state)
        task_mode = str(state.get("task_mode", "simple"))

        impl_outputs: list[dict[str, Any]] = []
        for agent_id in assignment.implementers:
            agent = self.app_cfg.agents[agent_id]
            prompt = render_template(
                self.impl_template,
                {
                    "loop_id": self.loop_cfg.loop_id,
                    "round_id": round_id,
                    "artifact_id": self.task_file.stem,
                    "objective": task_text,
                    "artifact_snapshot": current_artifact_snapshot,
                    "prioritized_fixes": json.dumps(prioritized_fixes, indent=2),
                    "task_mode": task_mode,
                    "workflow_context": workflow_context,
                    "selected_step_id": str(state.get("active_step_id", "")),
                    "schema_path": str(self.impl_schema_path),
                },
            )
            impl_output = self._run_with_schema_retry(
                agent_id=agent_id,
                role="IMPLEMENTER",
                prompt=prompt,
                schema_path=self.impl_schema_path,
                round_dir=round_dir,
            )
            impl_outputs.append(impl_output)

        selected_impl = impl_outputs[0]
        reviewer_outputs: list[dict[str, Any]] = []

        if len(impl_outputs) > 1 and assignment.reviewers:
            primary_reviewer = assignment.reviewers[0]
            best_score = -math.inf
            best_impl = impl_outputs[0]
            for candidate in impl_outputs:
                review_output = self._review_artifact(
                    reviewer_id=primary_reviewer,
                    round_id=round_id,
                    artifact_payload=candidate,
                    task_text=task_text,
                    state=state,
                    round_dir=round_dir,
                )
                score = float(review_output.get("overall_score", 0))
                if score > best_score:
                    best_score = score
                    best_impl = candidate
                reviewer_outputs.append(review_output)
            selected_impl = best_impl

        self._apply_artifact(selected_impl)

        if len(assignment.reviewers) > 0 and (len(impl_outputs) == 1):
            for reviewer_id in assignment.reviewers:
                review_output = self._review_artifact(
                    reviewer_id=reviewer_id,
                    round_id=round_id,
                    artifact_payload=selected_impl,
                    task_text=task_text,
                    state=state,
                    round_dir=round_dir,
                )
                reviewer_outputs.append(review_output)

        merged_review = _merge_reviews(reviewer_outputs)

        eval_result = run_eval_commands(
            self.app_cfg,
            self.loop_cfg.eval_commands,
            self.events_log,
            self.commands_log,
        )

        score = float(merged_review.get("overall_score", 0.0))
        red_flags = merged_review.get("red_flags") or []
        has_failure = (not eval_result.passed) or bool(red_flags)
        terminated = bool(
            eval_result.passed
            and score >= self.loop_cfg.score_threshold
            and not _has_blocking_fixes(merged_review)
        )

        parsed_dir = round_dir / "parsed"
        ensure_dir(parsed_dir)
        write_json(parsed_dir / "implementer.output.json", selected_impl)
        write_json(parsed_dir / "reviewers.outputs.json", reviewer_outputs)
        write_json(parsed_dir / "review.merged.json", merged_review)
        write_json(
            round_dir / "eval" / "results.json",
            {
                "passed": eval_result.passed,
                "commands": eval_result.commands,
            },
        )

        return RoundResult(
            round_id=round_id,
            assignment=assignment,
            implementer_output=selected_impl,
            reviewer_outputs=reviewer_outputs,
            merged_review=merged_review,
            eval_result=eval_result,
            score=score,
            terminated=terminated,
            failure=has_failure,
            rollback_applied=False,
        )

    def _review_artifact(
        self,
        reviewer_id: str,
        round_id: str,
        artifact_payload: dict[str, Any],
        task_text: str,
        state: dict[str, Any],
        round_dir: Path,
    ) -> dict[str, Any]:
        agent = self.app_cfg.agents[reviewer_id]
        prompt = render_template(
            self.rev_template,
            {
                "loop_id": self.loop_cfg.loop_id,
                "round_id": round_id,
                "artifact_id": self.task_file.stem,
                "acceptance_policy": task_text,
                "artifact_snapshot": json.dumps(artifact_payload, indent=2),
                "rubric": _default_rubric(self.loop_cfg.loop_id),
                "task_mode": str(state.get("task_mode", "simple")),
                "workflow_context": self._workflow_context_for_prompt(state),
                "selected_step_id": str(state.get("active_step_id", "")),
                "schema_path": str(self.rev_schema_path),
            },
        )
        return self._run_with_schema_retry(
            agent_id=reviewer_id,
            role="REVIEWER",
            prompt=prompt,
            schema_path=self.rev_schema_path,
            round_dir=round_dir,
        )

    def _run_with_schema_retry(
        self,
        agent_id: str,
        role: str,
        prompt: str,
        schema_path: Path,
        round_dir: Path,
    ) -> dict[str, Any]:
        agent = self.app_cfg.agents[agent_id]
        output, _ = self.executor.run_role(agent, role, prompt, schema_path, round_dir)
        errors = validate_with_schema(schema_path, output)
        if not errors:
            return output

        repair_prompt = (
            prompt
            + "\n\nYour last response failed JSON schema validation with these errors:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\nReturn valid JSON only, no markdown."
        )
        output, _ = self.executor.run_role(agent, role, repair_prompt, schema_path, round_dir)
        errors = validate_with_schema(schema_path, output)
        if errors:
            raise RuntimeError(f"{role} output invalid after retry: {errors}")
        return output

    def _apply_artifact(self, impl_output: dict[str, Any]) -> None:
        artifact = impl_output.get("artifact") or {}
        rel_path = artifact.get("path")
        content = artifact.get("content", "")
        if not rel_path:
            raise RuntimeError("Implementer output missing artifact.path")

        target = (self.app_cfg.workspace_root / rel_path).resolve()
        workspace = self.app_cfg.workspace_root.resolve()
        if workspace not in target.parents and target != workspace:
            raise RuntimeError(f"Artifact path escapes workspace: {target}")

        ensure_dir(target.parent)
        target.write_text(content, encoding="utf-8")

    def _load_artifact_snapshot(self, state: dict[str, Any]) -> str:
        latest_path = state.get("latest_artifact_path")
        if latest_path:
            candidate = (self.app_cfg.workspace_root / latest_path).resolve()
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8")
                    return text[:15000]
                except UnicodeDecodeError:
                    return "[binary artifact omitted]"
        return "[no artifact yet]"

    def _maybe_init_git(self, state: dict[str, Any]) -> None:
        if state["git_enabled"]:
            return
        enabled = is_git_repo(self.app_cfg.workspace_root)
        state["git_enabled"] = enabled
        if enabled and not state.get("git_initialized"):
            branch = f"codex/model-console/{self.run_id}"
            create_or_switch_branch(self.app_cfg.workspace_root, branch)
            state["git_initialized"] = True
            state["git_branch"] = branch
            self._save_state(state)

    def _load_or_init_state(self) -> dict[str, Any]:
        if self.resume and self.state_file.exists():
            with self.state_file.open("r", encoding="utf-8") as f:
                state = json.load(f)
            state = self._with_state_defaults(state)
            if not state.get("task_text"):
                state["task_text"] = self._read_task_text()
            self._ensure_workflow_state(state)
            self._save_state(state)
            return state

        if self.state_file.exists() and not self.resume:
            raise RuntimeError(
                f"Run `{self.run_id}` already exists. Use --resume or set a different --run-id"
            )

        task_text = self._read_task_text()
        state = {
            "run_id": self.run_id,
            "loop_id": self.loop_cfg.loop_id,
            "task_file": str(self.task_file),
            "task_text": task_text,
            "started_at": utc_now_iso(),
            "next_round_index": 0,
            "last_round_failed": False,
            "pending_fixes": [],
            "scores": [],
            "history": [],
            "terminated": False,
            "paused": False,
            "latest_artifact_path": "",
            "git_enabled": False,
            "git_initialized": False,
            "git_branch": "",
            "task_mode": "simple",
            "workflow_path": "",
            "workflow_phase": "plan",
            "completed_steps": [],
            "active_step_id": "",
            "no_progress_rounds": 0,
            "termination_reason": "",
            "workflow_steps": {},
            "integration_done": False,
            "current_step_attempts": 0,
        }
        self._ensure_workflow_state(state)
        write_json(
            self.run_dir / "run_manifest.json",
            {
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "task_file": str(self.task_file),
                "task_mode": state.get("task_mode", "simple"),
                "loop_config": asdict(self.loop_cfg),
            },
        )
        self._save_state(state)
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        write_json(self.state_file, state)

    def _read_task_text(self) -> str:
        if self.task_file.exists():
            return self.task_file.read_text(encoding="utf-8")
        if self.state_file.exists():
            try:
                with self.state_file.open("r", encoding="utf-8") as f:
                    prior_state = json.load(f)
                task_text = prior_state.get("task_text")
                if isinstance(task_text, str):
                    return task_text
            except (json.JSONDecodeError, OSError):
                pass
        raise FileNotFoundError(
            f"Task file not found and no cached task_text available: {self.task_file}"
        )

    def _get_task_text(self, state: dict[str, Any]) -> str:
        task_text = state.get("task_text")
        if isinstance(task_text, str) and task_text:
            return task_text
        task_text = self._read_task_text()
        state["task_text"] = task_text
        return task_text

    def _with_state_defaults(self, state: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "run_id": self.run_id,
            "loop_id": self.loop_cfg.loop_id,
            "task_file": str(self.task_file),
            "task_text": "",
            "started_at": utc_now_iso(),
            "next_round_index": 0,
            "last_round_failed": False,
            "pending_fixes": [],
            "scores": [],
            "history": [],
            "terminated": False,
            "paused": False,
            "latest_artifact_path": "",
            "git_enabled": False,
            "git_initialized": False,
            "git_branch": "",
            "task_mode": "simple",
            "workflow_path": "",
            "workflow_phase": "plan",
            "completed_steps": [],
            "active_step_id": "",
            "no_progress_rounds": 0,
            "termination_reason": "",
            "workflow_steps": {},
            "integration_done": False,
            "current_step_attempts": 0,
        }
        merged = {**defaults, **state}
        for key in ("pending_fixes", "scores", "history", "completed_steps"):
            if not isinstance(merged.get(key), list):
                merged[key] = list(defaults[key])  # type: ignore[index]
        if not isinstance(merged.get("workflow_steps"), dict):
            merged["workflow_steps"] = {}
        if not isinstance(merged.get("task_text"), str):
            merged["task_text"] = ""
        return merged

    def _ensure_workflow_state(self, state: dict[str, Any]) -> None:
        if self.loop_cfg.execution_mode != "dependency_workflow":
            state["task_mode"] = "simple"
            return

        complex_spec = _extract_complex_task_spec(self._get_task_text(state))
        if complex_spec is None:
            state["task_mode"] = "simple"
            return

        state["task_mode"] = "complex"
        if not state.get("workflow_path"):
            state["workflow_path"] = f"artifacts/{self.task_file.stem}.workflow.json"
        if not state.get("workflow_steps"):
            state["workflow_steps"] = _normalize_workflow_steps(complex_spec.get("steps") or [])
        if state.get("workflow_phase") not in {"plan", "execute", "integrate"}:
            state["workflow_phase"] = "plan"
        if not isinstance(state.get("completed_steps"), list):
            state["completed_steps"] = []
        valid_steps = set(state["workflow_steps"].keys())
        state["completed_steps"] = sorted(
            step_id for step_id in state["completed_steps"] if step_id in valid_steps
        )
        active_step = str(state.get("active_step_id", "") or "")
        if active_step and active_step != "__integrate__" and active_step not in valid_steps:
            state["active_step_id"] = ""
        if not valid_steps:
            state["task_mode"] = "simple"
            state["workflow_path"] = ""
            state["workflow_steps"] = {}
            return
        self._save_workflow_artifact(state)

    def _dependency_mode_active(self, state: dict[str, Any]) -> bool:
        return (
            self.loop_cfg.execution_mode == "dependency_workflow"
            and str(state.get("task_mode", "simple")) == "complex"
            and isinstance(state.get("workflow_steps"), dict)
            and bool(state.get("workflow_steps"))
        )

    def _invocation_round_limit(self, state: dict[str, Any]) -> int:
        if self._dependency_mode_active(state):
            return int(state.get("next_round_index", 0)) + self.loop_cfg.max_rounds
        return self.loop_cfg.max_rounds

    def _select_next_workflow_step(self, state: dict[str, Any]) -> dict[str, Any]:
        steps: dict[str, dict[str, Any]] = state.get("workflow_steps") or {}
        completed = set(state.get("completed_steps") or [])
        pending = sorted(step_id for step_id in steps.keys() if step_id not in completed)

        if pending:
            ready: list[str] = []
            for step_id in pending:
                depends_on = set(steps.get(step_id, {}).get("depends_on") or [])
                if depends_on.issubset(completed):
                    ready.append(step_id)
            if ready:
                chosen = self._select_step_from_fixes(ready, state.get("pending_fixes") or [])
                blocked = sorted(step_id for step_id in pending if step_id not in set(ready))
                return {
                    "status": "ready",
                    "step_id": chosen,
                    "ready_steps": ready,
                    "blocked_steps": blocked,
                }
            return {
                "status": "deadlock",
                "step_id": "",
                "ready_steps": [],
                "blocked_steps": pending,
            }

        if self.loop_cfg.require_final_integration_step and not state.get("integration_done", False):
            return {
                "status": "ready",
                "step_id": "__integrate__",
                "ready_steps": ["__integrate__"],
                "blocked_steps": [],
            }

        return {
            "status": "complete",
            "step_id": "",
            "ready_steps": [],
            "blocked_steps": [],
        }

    def _select_step_from_fixes(self, ready_steps: list[str], fixes: list[dict[str, Any]]) -> str:
        sorted_steps = sorted(ready_steps)
        for fix in fixes:
            text = f"{fix.get('fix', '')} {fix.get('rationale', '')}"
            for step_id in sorted_steps:
                if re.search(rf"\\b{re.escape(step_id)}\\b", text):
                    return step_id
        return sorted_steps[0]

    def _workflow_context_for_prompt(self, state: dict[str, Any]) -> str:
        if not self._dependency_mode_active(state):
            return "[workflow mode disabled]"
        snapshot = self._workflow_snapshot(state)
        return json.dumps(snapshot, indent=2, sort_keys=True)

    def _workflow_snapshot(self, state: dict[str, Any]) -> dict[str, Any]:
        steps: dict[str, dict[str, Any]] = state.get("workflow_steps") or {}
        completed = set(state.get("completed_steps") or [])
        selection = self._select_next_workflow_step(state)
        pending = sorted(step_id for step_id in steps.keys() if step_id not in completed)
        ready = selection.get("ready_steps") or []
        blocked = selection.get("blocked_steps") or []
        step_items = []
        for step_id in sorted(steps.keys()):
            spec = steps.get(step_id, {})
            status = "completed" if step_id in completed else "pending"
            if step_id in blocked:
                status = "blocked"
            if step_id in ready:
                status = "ready"
            step_items.append(
                {
                    "id": step_id,
                    "description": spec.get("description", ""),
                    "depends_on": spec.get("depends_on", []),
                    "done_when": spec.get("done_when", []),
                    "status": status,
                }
            )
        return {
            "task_mode": state.get("task_mode", "simple"),
            "phase": state.get("workflow_phase", "plan"),
            "active_step_id": state.get("active_step_id", ""),
            "completed_step_ids": sorted(completed),
            "pending_step_ids": pending,
            "ready_step_ids": ready,
            "blocked_step_ids": blocked,
            "current_step_attempts": int(state.get("current_step_attempts", 0)),
            "integration_required": bool(self.loop_cfg.require_final_integration_step),
            "integration_done": bool(state.get("integration_done", False)),
            "steps": step_items,
        }

    def _save_workflow_artifact(self, state: dict[str, Any], round_id: str | None = None) -> None:
        if not self._dependency_mode_active(state):
            return
        workflow_rel = str(state.get("workflow_path") or "")
        if not workflow_rel:
            return
        payload = self._workflow_snapshot(state)
        payload["task_id"] = self.task_file.stem
        payload["round_id"] = round_id or ""
        payload["termination_reason"] = str(state.get("termination_reason", ""))
        payload["no_progress_rounds"] = int(state.get("no_progress_rounds", 0))

        errors = validate_with_schema(self.workflow_schema_path, payload)
        if errors:
            raise RuntimeError(f"Workflow artifact invalid: {errors}")

        workflow_path = (self.app_cfg.workspace_root / workflow_rel).resolve()
        workspace = self.app_cfg.workspace_root.resolve()
        if workspace not in workflow_path.parents and workflow_path != workspace:
            raise RuntimeError(f"Workflow artifact path escapes workspace: {workflow_path}")
        write_json(workflow_path, payload)

        if round_id:
            checkpoint = self.checkpoints_dir / f"{round_id}.workflow.json"
            write_json(checkpoint, payload)

    def _update_workflow_after_round(
        self,
        state: dict[str, Any],
        round_result: RoundResult,
        round_dir: Path,
    ) -> None:
        if not self._dependency_mode_active(state):
            return
        del round_dir  # reserved for future round-level workflow diagnostics

        steps: dict[str, dict[str, Any]] = state.get("workflow_steps") or {}
        known_step_ids = set(steps.keys())
        completed_before = set(state.get("completed_steps") or [])
        progress = round_result.implementer_output.get("progress")
        progress_payload = progress if isinstance(progress, dict) else {}

        phase = str(progress_payload.get("phase", "")).lower()
        if phase in {"plan", "execute", "integrate"}:
            state["workflow_phase"] = phase

        completed_after = set(completed_before)
        raw_completed = progress_payload.get("completed_step_ids")
        if isinstance(raw_completed, list):
            for step_id in raw_completed:
                if isinstance(step_id, str) and step_id in known_step_ids:
                    completed_after.add(step_id)

        progress_made = len(completed_after) > len(completed_before)
        active_step = str(state.get("active_step_id", "") or "")
        if (
            active_step == "__integrate__"
            and self.loop_cfg.require_final_integration_step
            and phase == "integrate"
            and not round_result.failure
        ):
            state["integration_done"] = True
            progress_made = True

        if round_result.failure:
            progress_made = False

        state["completed_steps"] = sorted(completed_after)
        if active_step and active_step in completed_after:
            state["active_step_id"] = ""
        if active_step == "__integrate__" and state.get("integration_done", False):
            state["active_step_id"] = ""

        if progress_made:
            state["no_progress_rounds"] = 0
            state["current_step_attempts"] = 0
            if state.get("workflow_phase") == "plan":
                state["workflow_phase"] = "execute"
        else:
            state["no_progress_rounds"] = int(state.get("no_progress_rounds", 0)) + 1
            state["current_step_attempts"] = int(state.get("current_step_attempts", 0)) + 1

        if self._all_workflow_steps_completed(state) and not self.loop_cfg.require_final_integration_step:
            state["integration_done"] = True
            state["workflow_phase"] = "integrate"

        self._save_workflow_artifact(state, round_id=round_result.round_id)

    def _all_workflow_steps_completed(self, state: dict[str, Any]) -> bool:
        steps: dict[str, dict[str, Any]] = state.get("workflow_steps") or {}
        completed = set(state.get("completed_steps") or [])
        return bool(steps) and completed.issuperset(steps.keys())

    def _workflow_completion_ready(self, state: dict[str, Any]) -> bool:
        if not self._dependency_mode_active(state):
            return True
        if self.loop_cfg.require_dependency_closure and not self._all_workflow_steps_completed(state):
            return False
        if self.loop_cfg.require_final_integration_step and not state.get("integration_done", False):
            return False
        return True

    def _workflow_stagnated(self, state: dict[str, Any]) -> bool:
        if self.loop_cfg.stagnation_rounds <= 0:
            return False
        limit = self.loop_cfg.stagnation_rounds
        return int(state.get("no_progress_rounds", 0)) >= limit

    def _workflow_retry_exhausted(self, state: dict[str, Any]) -> bool:
        if self.loop_cfg.max_step_retries <= 0:
            return False
        max_retries = self.loop_cfg.max_step_retries
        return int(state.get("current_step_attempts", 0)) >= max_retries

    def _pause_workflow(self, state: dict[str, Any], reason: str, round_id: str) -> None:
        state["paused"] = True
        state["terminated"] = False
        state["termination_reason"] = reason
        self._save_workflow_artifact(state, round_id=round_id)
        self._save_state(state)
        append_jsonl(
            self.events_log,
            {
                "timestamp": utc_now_iso(),
                "event": "workflow_paused",
                "round_id": round_id,
                "reason": reason,
                "active_step_id": state.get("active_step_id", ""),
                "completed_steps": state.get("completed_steps", []),
            },
        )
        self._emit(
            {
                "timestamp": utc_now_iso(),
                "event": "workflow_paused",
                "round_id": round_id,
                "reason": reason,
                "active_step_id": state.get("active_step_id", ""),
                "completed_steps": state.get("completed_steps", []),
            }
        )

    def _read_swap_override(self) -> bool:
        override_file = self.run_dir / "overrides.json"
        if not override_file.exists():
            return False
        try:
            with override_file.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            return bool(payload.get("swap_next_round", False))
        except (json.JSONDecodeError, OSError):
            return False

    def _stagnated(self, scores: list[float]) -> bool:
        k = self.loop_cfg.stagnation_rounds
        if len(scores) < k + 1:
            return False
        recent = scores[-(k + 1) :]
        deltas = [abs(b - a) for a, b in zip(recent[:-1], recent[1:])]
        return all(delta <= self.loop_cfg.stagnation_epsilon for delta in deltas)

    def _write_reports(self, state: dict[str, Any]) -> dict[str, Any]:
        loop_report = {
            "run_id": state["run_id"],
            "loop_id": state["loop_id"],
            "rounds_executed": len(state["history"]),
            "scores": state["scores"],
            "terminated": bool(state.get("terminated", False)),
            "paused": bool(state.get("paused", False)),
            "termination_reason": str(state.get("termination_reason", "")),
            "task_mode": str(state.get("task_mode", "simple")),
            "history": state["history"],
            "git_branch": state.get("git_branch", ""),
            "workflow_path": state.get("workflow_path", ""),
            "active_step_id": state.get("active_step_id", ""),
            "completed_steps": state.get("completed_steps", []),
        }
        write_json(self.reports_dir / f"loop_{self.loop_cfg.loop_id}.json", loop_report)

        summary_md = self._format_summary_markdown(loop_report)
        (self.reports_dir / f"loop_{self.loop_cfg.loop_id}.md").write_text(
            summary_md, encoding="utf-8"
        )
        (self.reports_dir / "global_report.md").write_text(summary_md, encoding="utf-8")
        return loop_report

    def _format_summary_markdown(self, report: dict[str, Any]) -> str:
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

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_handler is not None:
            self.event_handler(event)


def _extract_complex_task_spec(task_text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(task_text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(task_text[idx:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("task_type", "")).lower() != "complex":
            continue
        steps = payload.get("steps")
        if isinstance(steps, list) and steps:
            return payload
    return None


def _normalize_workflow_steps(raw_steps: list[Any]) -> dict[str, dict[str, Any]]:
    steps: dict[str, dict[str, Any]] = {}
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        step_id = str(raw.get("id", "")).strip()
        if not step_id:
            continue
        depends_on = _string_list(raw.get("depends_on"))
        done_when = _string_list(raw.get("done_when"))
        steps[step_id] = {
            "description": str(raw.get("description", "")),
            "depends_on": sorted(set(depends_on)),
            "done_when": done_when,
        }

    if not steps:
        raise ValueError("ComplexTaskV1 must include at least one valid step")

    for step_id, spec in steps.items():
        for dep in spec.get("depends_on", []):
            if dep not in steps:
                raise ValueError(f"ComplexTaskV1 step `{step_id}` depends on unknown step `{dep}`")
            if dep == step_id:
                raise ValueError(f"ComplexTaskV1 step `{step_id}` cannot depend on itself")

    if _has_dependency_cycle(steps):
        raise ValueError("ComplexTaskV1 dependencies must be acyclic")
    return steps


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate:
            output.append(candidate)
    return output


def _has_dependency_cycle(steps: dict[str, dict[str, Any]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> bool:
        if step_id in visited:
            return False
        if step_id in visiting:
            return True
        visiting.add(step_id)
        for dep in steps.get(step_id, {}).get("depends_on", []):
            if visit(dep):
                return True
        visiting.remove(step_id)
        visited.add(step_id)
        return False

    for step_id in steps:
        if visit(step_id):
            return True
    return False


def _default_run_id(loop_id: str) -> str:
    return f"{loop_id}-{uuid4().hex[:8]}"


def _priority_rank(priority: str) -> int:
    ranks = {"P0": 0, "P1": 1, "P2": 2}
    return ranks.get(priority, 3)


def _merge_reviews(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    if not outputs:
        return {
            "status": "partial",
            "overall_score": 0,
            "critique": ["No reviewer outputs collected"],
            "prioritized_fixes": [],
            "acceptance_tests": [],
            "red_flags": ["No reviewer output"],
            "unsure": [],
        }

    scores = [float(o.get("overall_score", 0.0)) for o in outputs]
    merged: dict[str, Any] = {
        "status": "ok",
        "overall_score": round(sum(scores) / len(scores), 2),
        "critique": [],
        "prioritized_fixes": [],
        "acceptance_tests": [],
        "red_flags": [],
        "unsure": [],
    }

    fixes: list[dict[str, Any]] = []
    for output in outputs:
        if output.get("status") == "blocked":
            merged["status"] = "blocked"
        merged["critique"].extend(output.get("critique") or [])
        fixes.extend(output.get("prioritized_fixes") or [])
        merged["acceptance_tests"].extend(output.get("acceptance_tests") or [])
        merged["red_flags"].extend(output.get("red_flags") or [])
        merged["unsure"].extend(output.get("unsure") or [])

    dedup_tests = sorted(set(merged["acceptance_tests"]))
    dedup_red_flags = sorted(set(merged["red_flags"]))
    dedup_unsure = sorted(set(merged["unsure"]))
    dedup_critique = sorted(set(merged["critique"]))

    fixes.sort(key=lambda item: _priority_rank(str(item.get("priority", "P2"))))

    merged["prioritized_fixes"] = fixes
    merged["acceptance_tests"] = dedup_tests
    merged["red_flags"] = dedup_red_flags
    merged["unsure"] = dedup_unsure
    merged["critique"] = dedup_critique
    return merged


def _has_blocking_fixes(merged_review: dict[str, Any]) -> bool:
    for fix in merged_review.get("prioritized_fixes") or []:
        if str(fix.get("priority", "")).upper() == "P0":
            return True
    return False


def _round_commit_message(
    loop_id: str,
    round_id: str,
    assignment: Assignment,
    round_result: RoundResult,
) -> str:
    impl = ",".join(assignment.implementers)
    rev = ",".join(assignment.reviewers)
    return (
        f"loop:{loop_id} round:{round_id} impl:{impl} rev:{rev} score:{round_result.score}"
    )


def _round_history_entry(round_result: RoundResult, commit_sha: str | None) -> dict[str, Any]:
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


def _default_rubric(loop_id: str) -> str:
    if loop_id == "code_loop":
        return (
            "Correctness(35), Safety(20), Simplicity(15), Testability(15),"
            " Maintenability(15)."
        )
    if loop_id == "complex_reasoning_loop":
        return (
            "Dependency integrity(30), Step completion validity(25), Integration quality(20),"
            " Task adherence(15), Hallucination resistance(10)."
        )
    if loop_id == "plan_loop":
        return "Completeness(30), Sequencing(25), Risks(25), Verifiability(20)."
    return "Task adherence(40), Clarity(30), Hallucination resistance(30)."
