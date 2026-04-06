# Development Guide

This repository is a Python CLI application.

## Local Setup

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip setuptools wheel
py -m pip install -e .
```

## Common Commands

### Run the CLI

```bash
mc run --task tasks/inbox/T-001-bootstrap.md --loop bootstrap_loop
```

### Run Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Windows PowerShell:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

## Editing Prompt or Schema Contracts

When you change output shape expectations:

1. Update the schema in `schemas/`.
2. Update the relevant prompt template in `prompts/`.
3. Update parsing or transcript normalization if provider output shape changed.
4. Update or add tests in `tests/`.

Treat prompt/template/schema changes as one unit. Splitting them creates hard-to-debug failures.

## Adding a Provider

1. Add the agent definition in `config/agents.yaml`.
2. Extend provider command generation in `src/model_console/agents/command_builder.py`.
3. Extend provider trace extraction in `src/model_console/observability/transcript.py` if needed.
4. Add contract tests and hardening tests.
5. Document provider-specific behavior in `docs/configuration.md`.

## Adding a Loop

1. Add a loop entry to `config/loops.yaml`.
2. Pick implementer and reviewer pools.
3. Add or update a sample task if you want a runnable example.
4. Add tests only if the loop introduces new behavioral assumptions.

## Generated vs. Maintained Files

Maintain by hand:

- `src/model_console/**/*.py`
- `config/*.yaml`
- `prompts/*.txt`
- `schemas/*.json`
- `tests/*`
- `docs/*`

## Documentation Expectations

When you add or change behavior:

- update `README.md` if the user-facing workflow changes
- update `docs/` if the maintainer-facing mental model changes
- add comments only where the control flow or fallback logic is not obvious from names alone

This repo already uses module docstrings heavily. Prefer:

- docstrings for public modules/classes/helpers
- small comments above non-obvious logic blocks

Do not add comments that restate the next line of code.
