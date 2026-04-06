# Configuration

Runtime behavior is driven by three YAML files in `config/`.

## Files

- `config/agents.yaml`
  - Declares the available model agents and how to invoke them.
- `config/loops.yaml`
  - Declares orchestration loop behavior, role assignment strategy, thresholds, and eval commands.
- `config/policies.yaml`
  - Declares subprocess safety rules and timeouts.

## `agents.yaml`

Each agent defines one provider-backed model identity.

```yaml
agents:
  codex_primary:
    provider: codex
    model: gpt-5.3-codex
    cli_path: codex
    extra_args: []
    env: {}
```

### Fields

- `provider`
  - Supported built-ins are `claude`, `codex`, `copilot`, `gemini`, and `mock`.
- `model`
  - Provider model name.
  - `copilot_primary` may leave this blank to use the account default model.
- `cli_path`
  - Executable name or absolute path.
- `extra_args`
  - Appended to the generated provider command.
- `env`
  - Environment variables merged into the subprocess environment.

## `loops.yaml`

A loop describes how rounds are executed.

```yaml
loops:
  code_loop:
    artifact_kind: code
    max_rounds: 4
    score_threshold: 88
    stagnation_rounds: 2
    stagnation_epsilon: 0.5
    swap_next_round: false
    swap_on_failure: true
    role_assignment:
      strategy: round_robin
      implementers: [codex_primary]
      reviewers: [claude_primary]
      implementer_count: 1
      reviewer_count: 1
    eval_commands:
      - "pytest"
```

### Core Fields

- `artifact_kind`
  - Human-facing label inserted into prompt templates and reports.
- `max_rounds`
  - Maximum rounds this loop may execute in a single run.
- `score_threshold`
  - Acceptance threshold used by the engine after each review.
- `stagnation_rounds`
  - Number of low-change score windows before the run is considered stagnant.
- `stagnation_epsilon`
  - Maximum allowed score delta inside a stagnation window.
- `swap_next_round`
  - Swaps implementer/reviewer pools after each round.
- `swap_on_failure`
  - Swaps implementer/reviewer pools after a failed round.
- `eval_commands`
  - Shell commands run after each round.

### Role Assignment

`role_assignment` controls which configured agents fill each role.

- `strategy: static`
  - Always use the first `implementer_count` and `reviewer_count` agents from each pool.
- `strategy: round_robin`
  - Rotate through the pools each round.
- `strategy: rules_based`
  - Similar to round-robin, but shifts implementers after failures.

The same agent ID can appear in both pools. This is how loops like `live_reasoning_deep_codex_loop` or `live_reasoning_deep_copilot_loop` run the same provider as both implementer and reviewer.

### Dependency Workflow Options

These fields are only relevant when `execution_mode: dependency_workflow` is enabled:

- `max_step_retries`
- `require_dependency_closure`
- `require_final_integration_step`

## `policies.yaml`

Policies are enforced before subprocess execution.

```yaml
policies:
  allow_command_prefixes:
    - codex
    - copilot
    - python3
    - python
    - py
    - zsh
    - pwsh
    - powershell
  deny_command_patterns:
    - '(^|\\s)git\\s+reset\\s+--hard'
  run_timeout_seconds: 900
  model_timeout_seconds: 300
  max_completed_runs: 50
```

### Fields

- `allow_command_prefixes`
  - Only commands starting with these executables are allowed.
  - Eval commands are wrapped in the platform shell automatically. Safety checks still validate the inner executable against this allowlist, so the same loop config works with `zsh` on macOS/Linux and PowerShell on Windows.
- `deny_command_patterns`
  - Regex patterns that block dangerous shell expressions.
- `run_timeout_seconds`
  - Timeout for eval commands.
- `model_timeout_seconds`
  - Timeout for provider CLI calls.
- `max_completed_runs`
  - Optional retention cap for completed runs under `runs/`.

## Provider Notes

### Claude

- Uses prompt mode with JSON output and an inline schema payload.

### Codex

- Uses `codex exec` with `--json`, `--output-schema`, and `--output-last-message`.

### Copilot

- Uses non-interactive prompt mode with JSONL output.
- Supports workspace-scoped access via `--add-dir`.
- The default `copilot_primary` agent is configured to use the account default model.

### Gemini

- Uses prompt mode with JSON output and explicit included directories.

### Mock

- Used for offline smoke tests and test fixtures.
- If `cli_path: python3` is configured but `python3` is unavailable on the host, the runtime falls back to the current Python interpreter automatically.

## Validation Behavior

Config loading now rejects:

- invalid YAML
- sections that are not mappings
- agents without string `provider` or `model` fields
- empty loop sets or agent sets

That fail-fast behavior is intentional. Configuration errors should surface at startup, not in the middle of a run.
