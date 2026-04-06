# Repo Map

This document is a quick file-system guide for new maintainers.

## Top Level

### `src/model_console/`

Python backend and orchestration runtime.

### `config/`

Runtime configuration for agents, loops, and safety policies.

### `prompts/`

Prompt templates used to render implementer and reviewer instructions.

### `schemas/`

JSON schemas that define valid model output contracts.

### `tests/`

Unit and integration-style tests for backend behavior and transcript handling.

### `tasks/inbox/`

Sample and working task inputs.

### `runs/`

Generated runtime output. This directory is created as runs execute.

## Backend Module Map

| Path | Responsibility |
| --- | --- |
| `src/model_console/cli/app.py` | Terminal entry point, command parsing, and run retention handling |
| `src/model_console/core/engine.py` | Run lifecycle, round execution, workflow mode, and reports |
| `src/model_console/agents/executor.py` | Provider CLI invocation and normalized output handling |
| `src/model_console/observability/transcript.py` | Provider stdout normalization into a shared trace model |
| `src/model_console/contracts/config.py` | YAML loading and config validation |
| `src/model_console/core/role_assignment.py` | Implementer/reviewer pool selection |
| `src/model_console/agents/eval.py` | Post-round eval command execution |
| `src/model_console/core/gitops.py` | Git branch, commit, diff, and revert helpers |
| `src/model_console/safety/command_policy.py` | Command allowlist, deny-pattern enforcement, and redaction |
| `src/model_console/observability/transcript_viewer.py` | HTML transcript rendering |
| `src/model_console/json_utils.py` | Robust JSON-object extraction from model output |
| `src/model_console/contracts/prompts.py` | Prompt template loading and rendering |
| `src/model_console/contracts/validator.py` | JSON-schema validation wrapper |
| `src/model_console/agents/mock.py` | Offline mock provider used in tests and smoke runs |
| `src/model_console/models.py` | Shared dataclasses |
| `src/model_console/observability/logging.py` | Shared logging and JSON-writing helpers |
| `src/model_console/*.py` | Thin compatibility wrappers for legacy import paths |

## Tests

| File | Responsibility |
| --- | --- |
| `tests/observability/test_transcript.py` | Provider parsing, transcript artifacts, and prompt/executor contracts |
| `tests/observability/test_transcript_viewer.py` | Transcript viewer rendering and CLI integration |
| `tests/core/test_engine_helpers.py` | Review merge and run-state helper coverage |
| `tests/core/test_refactor_helpers.py` | Path helper and command-builder regression coverage |
| `tests/test_hardening.py` | Failure-path and resilience coverage |
| `tests/test_package_layout.py` | `src/` layout and compatibility-wrapper regression coverage |

## Recommended Reading Order

1. `README.md`
2. `docs/architecture.md`
3. `docs/configuration.md`
4. `docs/runs-and-artifacts.md`
5. `src/model_console/core/engine.py`
6. `src/model_console/agents/executor.py`
