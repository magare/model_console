# Model Console (V1 scaffold)

Local-first orchestration runner for iterative IMPLEMENTER/REVIEWER loops, with role swapping, JSON contracts, run logs, and git checkpoints.

## What this gives you

- Role-agnostic loop engine (`IMPLEMENTER` and `REVIEWER` are config roles, not hardcoded to one model)
- Round-based orchestration with optional role swaps
- Strict JSON schema validation for both roles
- Per-run logs, prompts, raw outputs, parsed outputs, and reports
- Safety policy (allowlist + deny patterns)
- Git branch-per-run and commit-per-round with rollback via `git revert`
- Resume support (`mc resume --run-id ...`)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

If you install with macOS Xcode system Python outside a virtualenv, editable install can fail because user site-packages may be disabled.

## Quick smoke test (no external model CLI needed)

```bash
mc run --task tasks/inbox/T-001-bootstrap.md --loop bootstrap_loop
```

This uses mock agents and produces artifacts/logs in `runs/<run_id>/...`.
Live progress is shown by default (use `--no-live` to disable).

## Command reference

### CLI help

```bash
mc --help
mc run --help
mc resume --help
mc status --help
```

### Check model CLIs

```bash
claude --version
codex --version
gemini --version
```

### Run loops

```bash
# Mock-only smoke loop
mc run --task tasks/inbox/T-001-bootstrap.md --loop bootstrap_loop --run-id bootstrap-001

# Real Codex/Gemini reasoning loop
mc run --task tasks/inbox/T-003-live-reasoning-test.md --loop live_reasoning_loop --run-id run-001

# Code loop (edit eval commands in config first)
mc run --task tasks/inbox/T-002-real-task.md --loop code_loop --run-id code-001

# Complex dependency-aware loop
mc run --task tasks/inbox/T-006-complex-template.md --loop complex_reasoning_loop --run-id complex-001
```

### Complex task format (ComplexTaskV1)

Use a JSON object in the task file with `task_type: "complex"` and a `steps` DAG.
When present, `complex_reasoning_loop` runs dependency-aware execution with checkpointed workflow state.

```json
{
  "task_type": "complex",
  "objective": "Ship feature X with migration and docs",
  "deliverables": ["feature code", "migration", "docs"],
  "constraints": ["deterministic output"],
  "steps": [
    {"id": "s01", "description": "Design API", "depends_on": [], "done_when": ["file_exists(specs/api.md)"]},
    {"id": "s02", "description": "Implement API", "depends_on": ["s01"], "done_when": ["file_exists(src/api.ts)"]},
    {"id": "s03", "description": "Write docs", "depends_on": ["s02"], "done_when": ["file_exists(docs/api.md)"]}
  ]
}
```

### Live mode

```bash
# live output is default
mc run --task tasks/inbox/T-003-live-reasoning-test.md --loop live_reasoning_loop --run-id run-002 --live

# disable live output
mc run --task tasks/inbox/T-003-live-reasoning-test.md --loop live_reasoning_loop --run-id run-003 --no-live
```

### Resume and status

```bash
mc status --run-id run-001
mc resume --run-id run-001
```

### Find available run IDs

```bash
ls -1 runs
find runs -maxdepth 2 -name state.json | sort
```

### Inspect logs and model outputs

```bash
# Timeline + command dispatch/completion
tail -n 100 runs/run-001/logs/events.jsonl
tail -n 100 runs/run-001/logs/commands.jsonl

# Round-level raw model outputs
cat runs/run-001/loop_live_reasoning_loop/rounds/r01/raw/implementer.last_message.txt
cat runs/run-001/loop_live_reasoning_loop/rounds/r01/raw/reviewer.stdout.log
```

### Optional cleanup for broken old installs

```bash
python3 -m pip uninstall -y UNKNOWN
```

## File layout

- `model_console/`: runner implementation
- `config/`: agents/loops/policies
- `prompts/`: role-based prompt templates
- `schemas/`: strict JSON contracts
- `runs/`: generated run state/logs/reports/artifacts

## Notes

- By default, `code_loop` includes placeholder eval commands. Replace with project-specific checks.
- Safety deny patterns block common destructive commands.
- CLI path args are workspace-confined: `--task`, `--runs-dir`, `--config-dir`, `--schemas-dir`, and `--prompts-dir` must resolve inside `--workspace`.
- For deterministic runs, pin CLI versions and model IDs in your environment.
