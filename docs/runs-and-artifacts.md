# Runs and Artifacts

Every run writes a self-contained directory under `runs/<run_id>/`.

## Directory Layout

```text
runs/<run_id>/
  state.json
  run_manifest.json
  logs/
    events.jsonl
    commands.jsonl
    transcript.jsonl
  reports/
    loop_<loop_id>.json
    loop_<loop_id>.md
    global_report.md
    transcript_viewer.html
  loop_<loop_id>/
    checkpoints/
    rounds/
      r01/
        prompts/
        raw/
        trace/
        artifacts/
```

## Important Files

### `state.json`

The engine’s authoritative persisted state.

Typical fields include:

- `next_round_index`
- `scores`
- `history`
- `terminated`
- `paused`
- `latest_artifact_path`
- workflow fields for dependency-mode loops

`mc resume` reads this file, validates required fields, and continues the run.

### `run_manifest.json`

A lightweight manifest with the run ID, loop ID, task file path, task mode, and loop config snapshot.

### `logs/events.jsonl`

High-level orchestration events such as:

- `loop_started`
- `roles_assigned`
- `model_command_started`
- `model_command_completed`
- `round_failed`
- `workflow_paused`

### `logs/commands.jsonl`

Subprocess command records for both provider invocations and eval commands.

### `logs/transcript.jsonl`

Normalized transcript stream across the whole run. This is the best source when you want to reconstruct what the orchestrator and providers said without reading raw provider stdout.

## Round Artifacts

Each round keeps separate `prompts`, `raw`, and `trace` subdirectories.

### `prompts/`

- Immutable attempt-specific prompt files
- `implementer.prompt.txt` and `reviewer.prompt.txt` latest aliases

### `raw/`

- provider stdout/stderr logs per attempt
- latest aliases for current attempt
- `last_message.txt` snapshots used by providers that emit final text out-of-band

### `trace/`

- normalized provider trace JSON files
- round-local `conversation.jsonl`

## Reports

### `reports/loop_<loop_id>.json`

Machine-readable loop summary:

- round count
- scores
- termination state
- round history
- workflow summary

### `reports/loop_<loop_id>.md`

Human-readable markdown summary for the specific loop.

### `reports/global_report.md`

Currently mirrors the loop markdown summary for the active run.

## Transcript Viewer

Use:

```bash
mc transcript --run-id <run_id>
```

This renders an HTML viewer for the normalized transcript. It is the easiest way to inspect long runs without manually reading JSONL.

## Complex Workflow Checkpoints

Dependency-workflow runs may write:

- `loop_<loop_id>/checkpoints/<round_id>.workflow.json`

These snapshots capture workflow-step progress after each round.

## Debugging Tips

### A model command failed

Read:

- `logs/events.jsonl`
- `logs/commands.jsonl`
- `loop_<loop_id>/rounds/<round_id>/raw/*.stderr.log`

### JSON output was malformed

Read:

- `loop_<loop_id>/rounds/<round_id>/raw/*.last_message.txt`
- `loop_<loop_id>/rounds/<round_id>/trace/*.provider_trace.json`

### Resume did not work

Read:

- `state.json`
- `run_manifest.json`

The resume path requires a readable JSON object with non-empty `loop_id` and `task_file` fields.
