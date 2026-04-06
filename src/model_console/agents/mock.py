"""Mock agent for local/CI testing.

Produces deterministic IMPLEMENTER or REVIEWER JSON payloads without
calling any real AI model, allowing end-to-end loop testing offline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..observability.logging import utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock model agent for local tests")
    parser.add_argument("--role", required=True, choices=["IMPLEMENTER", "REVIEWER"])
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--model-id", required=True)
    args = parser.parse_args()

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    loop_id = "unknown_loop"
    round_id = "r00"
    artifact_id = "artifact"
    for line in prompt_text.splitlines():
        if line.startswith("Loop:"):
            parts = line.replace(":", "").split()
            if len(parts) >= 6:
                loop_id = parts[1]
                round_id = parts[3]
                artifact_id = parts[5]

    if args.role == "IMPLEMENTER":
        payload = {
            "meta": {
                "model_id": args.model_id,
                "role": "IMPLEMENTER",
                "loop_id": loop_id,
                "round_id": round_id,
                "artifact_id": artifact_id,
                "timestamp": utc_now_iso(),
                "tool_version": "mock-agent 1.0",
            },
            "status": "ok",
            "artifact": {
                "kind": "spec",
                "path": "artifacts/PRD_Screen_Studio_Chrome_Extension_v1.md",
                "content": f"# Mock artifact\n\nGenerated in {round_id}.\n",
            },
            "change_summary": ["Generated deterministic mock artifact content"],
            "risk_notes": [],
            "todos": ["Replace mock provider with real CLI provider"],
            "progress": {
                "phase": "plan",
                "selected_step_id": "",
                "completed_step_ids": [],
                "pending_step_ids": [],
                "blocked_step_ids": [],
            },
            "unsure": [],
        }
    else:
        payload = {
            "meta": {
                "model_id": args.model_id,
                "role": "REVIEWER",
                "loop_id": loop_id,
                "round_id": round_id,
                "artifact_id": artifact_id,
                "timestamp": utc_now_iso(),
                "tool_version": "mock-agent 1.0",
            },
            "status": "ok",
            "overall_score": 90,
            "critique": ["Structure is acceptable for bootstrap testing."],
            "prioritized_fixes": [
                {
                    "priority": "P2",
                    "fix": "Replace placeholder artifact path once real task is known.",
                    "rationale": "Mock output is generic by design.",
                }
            ],
            "acceptance_tests": ["Artifact file exists and is non-empty"],
            "red_flags": [],
            "workflow_checks": {
                "dependency_ok": True,
                "step_done_claim_ok": True,
                "deadlock_detected": False,
            },
            "unsure": [],
        }

    print(json.dumps(payload))


if __name__ == "__main__":
    main()
