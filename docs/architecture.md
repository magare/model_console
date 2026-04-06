# Architecture

`model_console` is a local-first orchestration system for running iterative `IMPLEMENTER` and `REVIEWER` loops against model CLIs.

## High-Level Flow

1. A task file is selected from `tasks/inbox` or supplied directly to `mc run`.
2. `model_console.cli` delegates to `src/model_console/cli/app.py` to load config, schemas, and prompt templates.
3. `model_console.engine.LoopEngine` delegates to `src/model_console/core/engine.py` to create a run directory, initialize state, and assign roles for the next round.
4. `model_console.executors.AgentExecutor` delegates to `src/model_console/agents/executor.py` to invoke the configured model CLIs and capture prompt, stdout, stderr, normalized transcript events, and provider traces.
5. The implementer and reviewer payloads are validated against JSON schemas.
6. The engine writes artifacts, runs eval commands, scores the review outcome, and optionally commits or rolls back Git changes.
7. Reports, logs, and transcript views are written under `runs/<run_id>/...`.

## Main Components

### Entry Points

- `model_console.cli`
  - Compatibility package for the terminal entry point implemented in `src/model_console/cli/app.py`.
- `model_console.__main__`
  - `python -m model_console` wrapper around the CLI.

### Orchestration Core

- `model_console.engine`
  - Compatibility wrapper for `src/model_console/core/engine.py`, which owns run lifecycle, round execution, schema validation, scoring, evals, Git checkpoints, and dependency-workflow mode.
- `model_console.role_assignment`
  - Compatibility wrapper for `src/model_console/core/role_assignment.py`.
- `model_console.executors`
  - Compatibility wrapper for `src/model_console/agents/executor.py`, which uses `src/model_console/agents/command_builder.py` for provider-specific CLI commands.
- `model_console.transcript`
  - Compatibility wrapper for `src/model_console/observability/transcript.py`, which converts provider-specific stdout formats into a shared `ProviderTrace` model.

### Contracts and Prompting

- `model_console.config`
  - Compatibility wrapper for `src/model_console/contracts/config.py`, which loads and validates `config/agents.yaml`, `config/loops.yaml`, and `config/policies.yaml`.
- `model_console.prompts`
  - Compatibility wrapper for `src/model_console/contracts/prompts.py`.
- `model_console.validator`
  - Compatibility wrapper for `src/model_console/contracts/validator.py`.

### Runtime Support

- `model_console.eval`
  - Compatibility wrapper for `src/model_console/agents/eval.py`.
- `model_console.gitops`
  - Compatibility wrapper for `src/model_console/core/gitops.py`.
- `model_console.logging_utils`
  - Compatibility wrapper for `src/model_console/observability/logging.py`.
- `model_console.safety`
  - Compatibility wrapper for `src/model_console/safety/command_policy.py`.

## Run Lifecycle

### Standard Loops

Standard loops execute a simple round sequence:

1. Assign implementer and reviewer agent IDs.
2. Render implementer prompt and execute provider CLI.
3. Validate implementer output and write the artifact.
4. Render reviewer prompt and execute reviewer CLI.
5. Merge review output, run eval commands, update state, and decide whether to continue.

### Dependency Workflow Loops

Loops with `execution_mode: dependency_workflow` use a task DAG from the task file:

- Steps are normalized into `workflow_steps`.
- The engine selects one executable step at a time based on dependencies.
- Progress is tracked across rounds.
- The loop can pause if the workflow deadlocks or stagnates.

## Extension Points

### Add a New Provider

1. Add an agent entry to `config/agents.yaml`.
2. Extend `src/model_console/agents/command_builder.py`.
3. Extend `src/model_console/observability/transcript.py` if the provider emits a unique stdout format.
4. Add tests in `tests/observability/test_transcript.py` and `tests/test_hardening.py`.

### Add a New Loop

1. Define it in `config/loops.yaml`.
2. Reuse or update prompt templates in `prompts/`.
3. Reuse or update schemas in `schemas/` if the output contract changes.
4. Add or adjust sample tasks in `tasks/inbox/`.

### Change the Output Contract

1. Update the JSON schema in `schemas/`.
2. Update prompt templates so models are asked for the new shape.
3. Update tests that validate parsing, schema checks, and transcripts.

## Read This Next

- `docs/configuration.md`
- `docs/runs-and-artifacts.md`
- `docs/development.md`
- `docs/repo-map.md`
