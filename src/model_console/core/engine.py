"""Core orchestration engine (LoopEngine).

Runs iterative implement → review rounds until the artifact is accepted, scores
stagnate, or the max-rounds cap is reached.  Features:
  - Role assignment with static / round-robin / rules-based strategies.
  - JSON-schema validation with one auto-retry on malformed agent output.
  - Git branching, per-round diffs, and automatic rollback on failure.
  - Dependency-workflow mode for complex multi-step tasks.
  - Eval-command execution between rounds.
  - Full event and command logging (JSONL).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agents.eval import run_eval_commands
from ..agents.executor import AgentExecutor
from .gitops import (
    capture_diff,
    commit_all,
    create_or_switch_branch,
    head_sha,
    is_git_repo,
    revert_commit,
)
from ..observability.logging import append_jsonl, ensure_dir, utc_now_iso, write_json
from ..models import AppConfig, Assignment, LoopConfig, RoundResult
from ..contracts.prompts import load_template, render_template
from ..observability.reporting import (
    build_loop_report,
    format_summary_markdown,
    round_commit_message as _round_commit_message,
    round_history_entry as _round_history_entry,
)
from .reviews import (
    default_rubric as _default_rubric,
    has_blocking_fixes as _has_blocking_fixes,
    merge_reviews as _merge_reviews,
)
from .role_assignment import AssignmentContext, RoleAssignmentEngine
from .run_state import RunState, build_initial_state, run_manifest_payload, with_state_defaults
from ..observability.transcript import append_transcript_entry
from ..contracts.validator import validate_with_schema
from .workflow import (
    INTEGRATION_STEP_ID,
    TASK_MODE_COMPLEX,
    TASK_MODE_SIMPLE,
    WORKFLOW_PHASE_EXECUTE,
    WORKFLOW_PHASE_INTEGRATE,
    WORKFLOW_PHASE_PLAN,
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_DEADLOCK,
    extract_complex_task_spec as _extract_complex_task_spec,
    normalize_workflow_steps as _normalize_workflow_steps,
)


class LoopEngine:
    """Coordinate one persisted multi-round run for a configured loop."""

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
        self.transcript_log = self.logs_dir / "transcript.jsonl"

        self.executor = AgentExecutor(
            app_cfg,
            self.events_log,
            self.commands_log,
            transcript_log=self.transcript_log,
            event_handler=event_handler,
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

        if state["terminated"]:
            return self._write_reports(state)

        if state["paused"]:
            state["paused"] = False
            state["termination_reason"] = ""
            self._save_state(state)

        invocation_round_limit = self._invocation_round_limit(state)

        self._log_event(
            "loop_started",
            run_id=self.run_id,
            loop_id=self.loop_cfg.loop_id,
            task_file=str(self.task_file),
            invocation_round_limit=invocation_round_limit,
        )

        while state["next_round_index"] < invocation_round_limit:
            # Dependency-workflow mode chooses the next runnable DAG step before
            # each round and can pause the run if no further progress is possible.
            if self._dependency_mode_active(state):
                selection = self._select_next_workflow_step(state)
                if selection["status"] == WORKFLOW_STATUS_COMPLETE:
                    state["termination_reason"] = "workflow_complete"
                    state["terminated"] = True
                    self._save_state(state)
                    break
                if selection["status"] == WORKFLOW_STATUS_DEADLOCK:
                    self._pause_workflow(
                        state,
                        reason="workflow_deadlock",
                        round_id=f"r{state['next_round_index'] + 1:02d}",
                    )
                    break
                next_step_id = str(selection.get("step_id", ""))
                if state["active_step_id"] != next_step_id:
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

            self._log_event(
                "roles_assigned",
                round_id=round_id,
                implementers=assignment.implementers,
                reviewers=assignment.reviewers,
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
                self._log_event("round_failed", round_id=round_id, error=str(exc))
                self._save_state(state)
                if self.loop_cfg.swap_on_failure:
                    state["next_round_index"] += 1
                    if self._dependency_mode_active(state):
                        state["no_progress_rounds"] += 1
                        state["current_step_attempts"] += 1
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

                # A failed round is committed first for traceability, then reverted
                # so the workspace returns to the last accepted state.
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
                self._log_event(
                    "terminated_stagnation",
                    round_id=round_id,
                    scores=state["scores"],
                )
                self._save_state(state)
                break

        if (
            not state["terminated"]
            and not state["paused"]
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
        self._log_event(
            "loop_completed",
            run_id=self.run_id,
            loop_id=self.loop_cfg.loop_id,
            rounds_executed=len(state["history"]),
            scores=state["scores"],
            paused=state["paused"],
            termination_reason=state["termination_reason"],
        )
        return report

    def _run_round(
        self,
        round_id: str,
        round_dir: Path,
        assignment: Assignment,
        state: RunState,
    ) -> RoundResult:
        task_text = self._get_task_text(state)
        current_artifact_snapshot = self._load_artifact_snapshot(state)
        prioritized_fixes = state["pending_fixes"]
        workflow_context = self._workflow_context_for_prompt(state)
        task_mode = state["task_mode"]

        impl_outputs = self._execute_implementers(
            round_id=round_id,
            round_dir=round_dir,
            assignment=assignment,
            task_text=task_text,
            current_artifact_snapshot=current_artifact_snapshot,
            prioritized_fixes=prioritized_fixes,
            workflow_context=workflow_context,
            task_mode=task_mode,
            state=state,
        )
        selected_impl, reviewer_outputs = self._select_best_implementer(
            round_id=round_id,
            round_dir=round_dir,
            assignment=assignment,
            task_text=task_text,
            state=state,
            impl_outputs=impl_outputs,
        )
        self._apply_artifact(selected_impl)
        reviewer_outputs.extend(
            self._execute_reviewers(
                round_id=round_id,
                round_dir=round_dir,
                assignment=assignment,
                task_text=task_text,
                state=state,
                selected_impl=selected_impl,
                impl_outputs=impl_outputs,
            )
        )
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
        self._persist_round_result(
            round_dir=round_dir,
            selected_impl=selected_impl,
            reviewer_outputs=reviewer_outputs,
            merged_review=merged_review,
            eval_result=eval_result,
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

    def _execute_implementers(
        self,
        *,
        round_id: str,
        round_dir: Path,
        assignment: Assignment,
        task_text: str,
        current_artifact_snapshot: str,
        prioritized_fixes: list[dict[str, Any]],
        workflow_context: str,
        task_mode: str,
        state: RunState,
    ) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for agent_id in assignment.implementers:
            prompt = render_template(
                self.impl_template,
                {
                    "loop_id": self.loop_cfg.loop_id,
                    "round_id": round_id,
                    "artifact_id": self.task_file.stem,
                    "artifact_kind": self.loop_cfg.artifact_kind,
                    "objective": task_text,
                    "artifact_snapshot": current_artifact_snapshot,
                    "prioritized_fixes": json.dumps(prioritized_fixes, indent=2),
                    "task_mode": task_mode,
                    "workflow_context": workflow_context,
                    "selected_step_id": state["active_step_id"],
                    "schema_path": str(self.impl_schema_path),
                },
            )
            outputs.append(
                self._run_with_schema_retry(
                    agent_id=agent_id,
                    role="IMPLEMENTER",
                    prompt=prompt,
                    schema_path=self.impl_schema_path,
                    round_dir=round_dir,
                )
            )
        return outputs

    def _select_best_implementer(
        self,
        *,
        round_id: str,
        round_dir: Path,
        assignment: Assignment,
        task_text: str,
        state: RunState,
        impl_outputs: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if len(impl_outputs) <= 1 or not assignment.reviewers:
            return impl_outputs[0], []

        primary_reviewer = assignment.reviewers[0]
        best_score = -math.inf
        best_impl = impl_outputs[0]
        reviewer_outputs: list[dict[str, Any]] = []
        for candidate in impl_outputs:
            review_output = self._review_artifact(
                reviewer_id=primary_reviewer,
                round_id=round_id,
                artifact_payload=candidate,
                task_text=task_text,
                state=state,
                round_dir=round_dir,
            )
            reviewer_outputs.append(review_output)
            score = float(review_output.get("overall_score", 0))
            if score > best_score:
                best_score = score
                best_impl = candidate
        return best_impl, reviewer_outputs

    def _execute_reviewers(
        self,
        *,
        round_id: str,
        round_dir: Path,
        assignment: Assignment,
        task_text: str,
        state: RunState,
        selected_impl: dict[str, Any],
        impl_outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(assignment.reviewers) == 0 or len(impl_outputs) != 1:
            return []

        outputs: list[dict[str, Any]] = []
        for reviewer_id in assignment.reviewers:
            self._append_transcript(
                round_dir,
                {
                    "timestamp": utc_now_iso(),
                    "event": "artifact_handoff",
                    "run_id": self.run_id,
                    "loop_id": self.loop_cfg.loop_id,
                    "round_id": round_id,
                    "speaker": assignment.implementers[0],
                    "recipient": reviewer_id,
                    "role": "REVIEWER",
                    "artifact_path": selected_impl.get("artifact", {}).get("path", ""),
                    "text": "Orchestrator forwarded the latest implementer artifact for review.",
                },
            )
            outputs.append(
                self._review_artifact(
                    reviewer_id=reviewer_id,
                    round_id=round_id,
                    artifact_payload=selected_impl,
                    task_text=task_text,
                    state=state,
                    round_dir=round_dir,
                )
            )
        return outputs

    def _persist_round_result(
        self,
        *,
        round_dir: Path,
        selected_impl: dict[str, Any],
        reviewer_outputs: list[dict[str, Any]],
        merged_review: dict[str, Any],
        eval_result: Any,
    ) -> None:
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

    def _review_artifact(
        self,
        reviewer_id: str,
        round_id: str,
        artifact_payload: dict[str, Any],
        task_text: str,
        state: RunState,
        round_dir: Path,
    ) -> dict[str, Any]:
        prompt = render_template(
            self.rev_template,
            {
                "loop_id": self.loop_cfg.loop_id,
                "round_id": round_id,
                "artifact_id": self.task_file.stem,
                "acceptance_policy": task_text,
                "artifact_snapshot": json.dumps(artifact_payload, indent=2),
                "rubric": _default_rubric(self.loop_cfg.loop_id),
                "task_mode": state["task_mode"],
                "workflow_context": self._workflow_context_for_prompt(state),
                "selected_step_id": state["active_step_id"],
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
        output, _ = self.executor.run_role(
            agent,
            run_id=self.run_id,
            loop_id=self.loop_cfg.loop_id,
            role=role,
            prompt=prompt,
            schema_path=schema_path,
            round_dir=round_dir,
            attempt_index=1,
        )
        errors = validate_with_schema(schema_path, output)
        if not errors:
            return output

        self._append_transcript(
            round_dir,
            {
                "timestamp": utc_now_iso(),
                "event": "schema_repair_requested",
                "run_id": self.run_id,
                "loop_id": self.loop_cfg.loop_id,
                "round_id": round_dir.name,
                "speaker": "orchestrator",
                "recipient": agent_id,
                "role": role,
                "text": "\n".join(errors),
            },
        )
        repair_prompt = (
            prompt
            + "\n\nYour last response failed JSON schema validation with these errors:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\nReturn valid JSON only, no markdown."
        )
        output, _ = self.executor.run_role(
            agent,
            run_id=self.run_id,
            loop_id=self.loop_cfg.loop_id,
            role=role,
            prompt=repair_prompt,
            schema_path=schema_path,
            round_dir=round_dir,
            attempt_index=2,
        )
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

    def _load_artifact_snapshot(self, state: RunState) -> str:
        latest_path = state["latest_artifact_path"]
        if latest_path:
            candidate = (self.app_cfg.workspace_root / latest_path).resolve()
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8")
                    return text[:15000]
                except UnicodeDecodeError:
                    return "[binary artifact omitted]"
        return "[no artifact yet]"

    def _maybe_init_git(self, state: RunState) -> None:
        if state["git_enabled"]:
            return
        enabled = is_git_repo(self.app_cfg.workspace_root)
        state["git_enabled"] = enabled
        if enabled and not state["git_initialized"]:
            branch = f"codex/model-console/{self.run_id}"
            create_or_switch_branch(self.app_cfg.workspace_root, branch)
            state["git_initialized"] = True
            state["git_branch"] = branch
            self._save_state(state)

    def _load_or_init_state(self) -> RunState:
        if self.resume and self.state_file.exists():
            with self.state_file.open("r", encoding="utf-8") as f:
                state = json.load(f)
            state = self._with_state_defaults(state)
            if not state["task_text"]:
                state["task_text"] = self._read_task_text()
            self._ensure_workflow_state(state)
            self._save_state(state)
            return state

        if self.state_file.exists() and not self.resume:
            raise RuntimeError(
                f"Run `{self.run_id}` already exists. Use --resume or set a different --run-id"
            )

        task_text = self._read_task_text()
        state = build_initial_state(
            run_id=self.run_id,
            loop_cfg=self.loop_cfg,
            task_file=self.task_file,
            task_text=task_text,
        )
        self._ensure_workflow_state(state)
        write_json(
            self.run_dir / "run_manifest.json",
            run_manifest_payload(
                run_id=self.run_id,
                loop_cfg=self.loop_cfg,
                task_file=self.task_file,
                task_mode=state["task_mode"],
            ),
        )
        self._save_state(state)
        return state

    def _save_state(self, state: RunState) -> None:
        write_json(self.state_file, state)

    def _read_task_text(self) -> str:
        if self.task_file.exists():
            try:
                return self.task_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass
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

    def _get_task_text(self, state: RunState) -> str:
        task_text = state["task_text"]
        if task_text:
            return task_text
        task_text = self._read_task_text()
        state["task_text"] = task_text
        return task_text

    def _with_state_defaults(self, state: dict[str, Any]) -> RunState:
        return with_state_defaults(
            state,
            run_id=self.run_id,
            loop_cfg=self.loop_cfg,
            task_file=self.task_file,
        )

    def _ensure_workflow_state(self, state: RunState) -> None:
        if self.loop_cfg.execution_mode != "dependency_workflow":
            state["task_mode"] = TASK_MODE_SIMPLE
            return

        complex_spec = _extract_complex_task_spec(self._get_task_text(state))
        if complex_spec is None:
            state["task_mode"] = TASK_MODE_SIMPLE
            return

        state["task_mode"] = TASK_MODE_COMPLEX
        if not state["workflow_path"]:
            state["workflow_path"] = f"artifacts/{self.task_file.stem}.workflow.json"
        if not state["workflow_steps"]:
            state["workflow_steps"] = _normalize_workflow_steps(complex_spec.get("steps") or [])
        if state["workflow_phase"] not in {
            WORKFLOW_PHASE_PLAN,
            WORKFLOW_PHASE_EXECUTE,
            WORKFLOW_PHASE_INTEGRATE,
        }:
            state["workflow_phase"] = WORKFLOW_PHASE_PLAN
        valid_steps = set(state["workflow_steps"].keys())
        state["completed_steps"] = sorted(
            step_id for step_id in state["completed_steps"] if step_id in valid_steps
        )
        active_step = state["active_step_id"]
        if active_step and active_step != INTEGRATION_STEP_ID and active_step not in valid_steps:
            state["active_step_id"] = ""
        if not valid_steps:
            state["task_mode"] = TASK_MODE_SIMPLE
            state["workflow_path"] = ""
            state["workflow_steps"] = {}
            return
        self._save_workflow_artifact(state)

    def _dependency_mode_active(self, state: RunState) -> bool:
        return (
            self.loop_cfg.execution_mode == "dependency_workflow"
            and state["task_mode"] == TASK_MODE_COMPLEX
            and bool(state["workflow_steps"])
        )

    def _invocation_round_limit(self, state: RunState) -> int:
        if self._dependency_mode_active(state):
            return state["next_round_index"] + self.loop_cfg.max_rounds
        return self.loop_cfg.max_rounds

    def _select_next_workflow_step(self, state: RunState) -> dict[str, Any]:
        steps = state["workflow_steps"]
        completed = set(state["completed_steps"])
        pending = sorted(step_id for step_id in steps.keys() if step_id not in completed)

        if pending:
            ready: list[str] = []
            for step_id in pending:
                depends_on = set(steps.get(step_id, {}).get("depends_on") or [])
                if depends_on.issubset(completed):
                    ready.append(step_id)
            if ready:
                chosen = self._select_step_from_fixes(ready, state["pending_fixes"])
                blocked = sorted(step_id for step_id in pending if step_id not in set(ready))
                return {
                    "status": WORKFLOW_STATUS_READY,
                    "step_id": chosen,
                    "ready_steps": ready,
                    "blocked_steps": blocked,
                }
            return {
                "status": WORKFLOW_STATUS_DEADLOCK,
                "step_id": "",
                "ready_steps": [],
                "blocked_steps": pending,
            }

        if self.loop_cfg.require_final_integration_step and not state["integration_done"]:
            return {
                "status": WORKFLOW_STATUS_READY,
                "step_id": INTEGRATION_STEP_ID,
                "ready_steps": [INTEGRATION_STEP_ID],
                "blocked_steps": [],
            }

        return {
            "status": WORKFLOW_STATUS_COMPLETE,
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

    def _workflow_context_for_prompt(self, state: RunState) -> str:
        if not self._dependency_mode_active(state):
            return "[workflow mode disabled]"
        snapshot = self._workflow_snapshot(state)
        return json.dumps(snapshot, indent=2, sort_keys=True)

    def _workflow_snapshot(self, state: RunState) -> dict[str, Any]:
        steps = state["workflow_steps"]
        completed = set(state["completed_steps"])
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
            "task_mode": state["task_mode"],
            "phase": state["workflow_phase"],
            "active_step_id": state["active_step_id"],
            "completed_step_ids": sorted(completed),
            "pending_step_ids": pending,
            "ready_step_ids": ready,
            "blocked_step_ids": blocked,
            "current_step_attempts": state["current_step_attempts"],
            "integration_required": bool(self.loop_cfg.require_final_integration_step),
            "integration_done": state["integration_done"],
            "steps": step_items,
        }

    def _save_workflow_artifact(self, state: RunState, round_id: str | None = None) -> None:
        if not self._dependency_mode_active(state):
            return
        workflow_rel = state["workflow_path"]
        if not workflow_rel:
            return
        payload = self._workflow_snapshot(state)
        payload["task_id"] = self.task_file.stem
        payload["round_id"] = round_id or ""
        payload["termination_reason"] = state["termination_reason"]
        payload["no_progress_rounds"] = state["no_progress_rounds"]

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
        state: RunState,
        round_result: RoundResult,
        round_dir: Path,
    ) -> None:
        if not self._dependency_mode_active(state):
            return
        del round_dir  # reserved for future round-level workflow diagnostics

        steps = state["workflow_steps"]
        known_step_ids = set(steps.keys())
        completed_before = set(state["completed_steps"])
        progress = round_result.implementer_output.get("progress")
        progress_payload = progress if isinstance(progress, dict) else {}

        phase = str(progress_payload.get("phase", "")).lower()
        if phase in {WORKFLOW_PHASE_PLAN, WORKFLOW_PHASE_EXECUTE, WORKFLOW_PHASE_INTEGRATE}:
            state["workflow_phase"] = phase

        completed_after = set(completed_before)
        raw_completed = progress_payload.get("completed_step_ids")
        if isinstance(raw_completed, list):
            for step_id in raw_completed:
                if isinstance(step_id, str) and step_id in known_step_ids:
                    completed_after.add(step_id)

        progress_made = len(completed_after) > len(completed_before)
        active_step = state["active_step_id"]
        if (
            active_step == INTEGRATION_STEP_ID
            and self.loop_cfg.require_final_integration_step
            and phase == WORKFLOW_PHASE_INTEGRATE
            and not round_result.failure
        ):
            state["integration_done"] = True
            progress_made = True

        if round_result.failure:
            progress_made = False

        state["completed_steps"] = sorted(completed_after)
        if active_step and active_step in completed_after:
            state["active_step_id"] = ""
        if active_step == INTEGRATION_STEP_ID and state["integration_done"]:
            state["active_step_id"] = ""

        if progress_made:
            state["no_progress_rounds"] = 0
            state["current_step_attempts"] = 0
            if state["workflow_phase"] == WORKFLOW_PHASE_PLAN:
                state["workflow_phase"] = WORKFLOW_PHASE_EXECUTE
        else:
            state["no_progress_rounds"] = state["no_progress_rounds"] + 1
            state["current_step_attempts"] = state["current_step_attempts"] + 1

        if self._all_workflow_steps_completed(state) and not self.loop_cfg.require_final_integration_step:
            state["integration_done"] = True
            state["workflow_phase"] = WORKFLOW_PHASE_INTEGRATE

        self._save_workflow_artifact(state, round_id=round_result.round_id)

    def _all_workflow_steps_completed(self, state: RunState) -> bool:
        steps = state["workflow_steps"]
        completed = set(state["completed_steps"])
        return bool(steps) and completed.issuperset(steps.keys())

    def _workflow_completion_ready(self, state: RunState) -> bool:
        if not self._dependency_mode_active(state):
            return True
        if self.loop_cfg.require_dependency_closure and not self._all_workflow_steps_completed(state):
            return False
        if self.loop_cfg.require_final_integration_step and not state["integration_done"]:
            return False
        return True

    def _workflow_stagnated(self, state: RunState) -> bool:
        if self.loop_cfg.stagnation_rounds <= 0:
            return False
        limit = self.loop_cfg.stagnation_rounds
        return state["no_progress_rounds"] >= limit

    def _workflow_retry_exhausted(self, state: RunState) -> bool:
        if self.loop_cfg.max_step_retries <= 0:
            return False
        max_retries = self.loop_cfg.max_step_retries
        return state["current_step_attempts"] >= max_retries

    def _pause_workflow(self, state: RunState, reason: str, round_id: str) -> None:
        state["paused"] = True
        state["terminated"] = False
        state["termination_reason"] = reason
        self._save_workflow_artifact(state, round_id=round_id)
        self._save_state(state)
        self._log_event(
            "workflow_paused",
            round_id=round_id,
            reason=reason,
            active_step_id=state["active_step_id"],
            completed_steps=state["completed_steps"],
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

    def _write_reports(self, state: RunState) -> dict[str, Any]:
        loop_report = build_loop_report(state)
        write_json(self.reports_dir / f"loop_{self.loop_cfg.loop_id}.json", loop_report)

        summary_md = format_summary_markdown(loop_report)
        (self.reports_dir / f"loop_{self.loop_cfg.loop_id}.md").write_text(
            summary_md, encoding="utf-8"
        )
        (self.reports_dir / "global_report.md").write_text(summary_md, encoding="utf-8")
        return loop_report

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_handler is not None:
            self.event_handler(event)

    def _append_transcript(self, round_dir: Path, payload: dict[str, Any]) -> None:
        append_transcript_entry(self.transcript_log, round_dir, payload)

    def _log_event(self, event_name: str, **fields: Any) -> None:
        payload = {
            "timestamp": utc_now_iso(),
            "event": event_name,
            **fields,
        }
        append_jsonl(self.events_log, payload)
        self._emit(payload)


def _default_run_id(loop_id: str) -> str:
    return f"{loop_id}-{uuid4().hex[:8]}"
