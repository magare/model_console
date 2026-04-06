"""Review aggregation and rubric helpers."""

from __future__ import annotations

from typing import Any


DEFAULT_RUBRICS = {
    "code_loop": "Correctness(35), Safety(20), Simplicity(15), Testability(15), Maintenability(15).",
    "complex_reasoning_loop": (
        "Dependency integrity(30), Step completion validity(25), Integration quality(20),"
        " Task adherence(15), Hallucination resistance(10)."
    ),
    "prompt_loop": "Completeness(30), Sequencing(25), Risks(25), Verifiability(20).",
}
FALLBACK_RUBRIC = "Task adherence(40), Clarity(30), Hallucination resistance(30)."


def merge_reviews(outputs: list[dict[str, Any]]) -> dict[str, Any]:
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

    scores = [float(output.get("overall_score", 0.0)) for output in outputs]
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

    fixes.sort(key=lambda item: priority_rank(str(item.get("priority", "P2"))))
    merged["prioritized_fixes"] = fixes
    merged["acceptance_tests"] = sorted(set(merged["acceptance_tests"]))
    merged["red_flags"] = sorted(set(merged["red_flags"]))
    merged["unsure"] = sorted(set(merged["unsure"]))
    merged["critique"] = sorted(set(merged["critique"]))
    return merged


def has_blocking_fixes(merged_review: dict[str, Any]) -> bool:
    for fix in merged_review.get("prioritized_fixes") or []:
        if str(fix.get("priority", "")).upper() == "P0":
            return True
    return False


def default_rubric(loop_id: str) -> str:
    return DEFAULT_RUBRICS.get(loop_id, FALLBACK_RUBRIC)


def priority_rank(priority: str) -> int:
    ranks = {"P0": 0, "P1": 1, "P2": 2}
    return ranks.get(priority, 3)
