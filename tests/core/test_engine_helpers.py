from __future__ import annotations

import unittest
from pathlib import Path

from model_console.models import LoopConfig, RoleAssignmentConfig


def _loop_config() -> LoopConfig:
    return LoopConfig(
        loop_id="bootstrap_loop",
        artifact_kind="plan",
        max_rounds=2,
        score_threshold=80.0,
        stagnation_rounds=1,
        stagnation_epsilon=0.1,
        swap_next_round=False,
        swap_on_failure=True,
        role_assignment=RoleAssignmentConfig(
            strategy="static",
            implementers=["mock_impl"],
            reviewers=["mock_rev"],
            implementer_count=1,
            reviewer_count=1,
        ),
    )


class ReviewHelperTests(unittest.TestCase):
    def test_merge_reviews_deduplicates_text_and_sorts_fixes_by_priority(self) -> None:
        from model_console.reviews import merge_reviews

        merged = merge_reviews(
            [
                {
                    "status": "ok",
                    "overall_score": 70,
                    "critique": ["Needs tests", "Needs docs"],
                    "prioritized_fixes": [
                        {"priority": "P2", "fix": "Add docs"},
                        {"priority": "P0", "fix": "Add tests"},
                    ],
                    "acceptance_tests": ["pytest -q"],
                    "red_flags": [],
                    "unsure": [],
                },
                {
                    "status": "blocked",
                    "overall_score": 90,
                    "critique": ["Needs tests"],
                    "prioritized_fixes": [{"priority": "P1", "fix": "Trim complexity"}],
                    "acceptance_tests": ["pytest -q", "python3 -m build"],
                    "red_flags": ["Blocking issue"],
                    "unsure": ["Need a second look"],
                },
            ]
        )

        self.assertEqual(merged["status"], "blocked")
        self.assertEqual(merged["overall_score"], 80.0)
        self.assertEqual(merged["critique"], ["Needs docs", "Needs tests"])
        self.assertEqual(
            [item["priority"] for item in merged["prioritized_fixes"]],
            ["P0", "P1", "P2"],
        )
        self.assertEqual(
            merged["acceptance_tests"],
            ["pytest -q", "python3 -m build"],
        )


class RunStateTests(unittest.TestCase):
    def test_build_initial_state_uses_shared_defaults(self) -> None:
        from model_console.run_state import build_initial_state

        state = build_initial_state(
            run_id="demo-run",
            loop_cfg=_loop_config(),
            task_file=Path("/tmp/demo-task.md"),
            task_text="Ship the bootstrap artifact.",
        )

        self.assertEqual(state["run_id"], "demo-run")
        self.assertEqual(state["task_mode"], "simple")
        self.assertEqual(state["pending_fixes"], [])
        self.assertEqual(state["workflow_steps"], {})

    def test_with_state_defaults_restores_invalid_collection_fields(self) -> None:
        from model_console.run_state import with_state_defaults

        merged = with_state_defaults(
            {
                "run_id": "demo-run",
                "pending_fixes": "bad",
                "scores": None,
                "history": "bad",
                "completed_steps": "bad",
                "workflow_steps": [],
            },
            run_id="demo-run",
            loop_cfg=_loop_config(),
            task_file=Path("/tmp/demo-task.md"),
        )

        self.assertEqual(merged["pending_fixes"], [])
        self.assertEqual(merged["scores"], [])
        self.assertEqual(merged["history"], [])
        self.assertEqual(merged["completed_steps"], [])
        self.assertEqual(merged["workflow_steps"], {})
