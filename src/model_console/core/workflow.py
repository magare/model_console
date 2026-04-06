"""Dependency-workflow parsing and constants."""

from __future__ import annotations

import json
from typing import Any


TASK_MODE_SIMPLE = "simple"
TASK_MODE_COMPLEX = "complex"
WORKFLOW_PHASE_PLAN = "plan"
WORKFLOW_PHASE_EXECUTE = "execute"
WORKFLOW_PHASE_INTEGRATE = "integrate"
WORKFLOW_STATUS_READY = "ready"
WORKFLOW_STATUS_DEADLOCK = "deadlock"
WORKFLOW_STATUS_COMPLETE = "complete"
INTEGRATION_STEP_ID = "__integrate__"


def extract_complex_task_spec(task_text: str) -> dict[str, Any] | None:
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
        if str(payload.get("task_type", "")).lower() != TASK_MODE_COMPLEX:
            continue
        steps = payload.get("steps")
        if isinstance(steps, list) and steps:
            return payload
    return None


def normalize_workflow_steps(raw_steps: list[Any]) -> dict[str, dict[str, Any]]:
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
