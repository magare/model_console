# Lessons

## 2026-03-03
- Correction: A `tasks/todo.md` alone is insufficient for autonomous orchestration.
- Rule: For workflow-engineering requests, deliver an executable control system scaffold (configs, schemas, prompts, runner scripts, run directories), not just planning docs.
- Rule: Present a concrete operator loop (`one command to run`) with persisted state and restart/resume behavior.
- Correction: Operational instructions must account for missing/nonexistent run IDs and provide a discovery path.
- Rule: When giving run commands, always include a follow-up check to list available runs and clarify that `status` requires an existing `runs/<run-id>/state.json`.
- Correction: Users need visible runtime orchestration signals, not only files/logs after completion.
- Rule: Default CLI runs should emit concise live events (loop start, role assignment, model dispatch/completion, failures).
