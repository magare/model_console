# Workflow Plan: Model Console Orchestration (Implemented V1 Scaffold + Live CLI Test)

## Tasks
- [x] Gather latest official docs for Claude Code CLI (interactive/non-interactive, permissions, output format)
- [x] Gather latest official docs for Codex CLI (exec mode, config, model/provider/auth, machine-readable outputs)
- [x] Gather latest official docs for Gemini CLI (headless mode, options, config, sandbox/trust)
- [x] Design role-agnostic architecture for multi-loop orchestration
- [x] Define loop engine state machine + role assignment/swap policies
- [x] Define strict JSON I/O contracts + examples for Implementer/Reviewer
- [x] Define role-based prompting templates with injection resistance and anti-hallucination rules
- [x] Implement `mc` CLI (`run`, `resume`, `status`) with persistent run state
- [x] Implement loop engine with assignment, schema validation, termination, and stagnation detection
- [x] Implement model execution adapters (Claude/Codex/Gemini + mock provider)
- [x] Implement safety policies (allowlist + deny patterns + redaction)
- [x] Implement evaluation runner and per-round command logging
- [x] Implement git integration hooks (branch-per-run, commit-per-round, rollback-by-revert)
- [x] Add default configs, schemas, prompt templates, and onboarding docs
- [x] Run end-to-end bootstrap verification using mock agents
- [x] Run live host-orchestrated integration test with Codex + Gemini reasoning agents

## Review
- Verification:
  - `python3 -m compileall model_console` passed.
  - `python3 -m model_console --help` passed.
  - `python3 -m model_console run --task tasks/inbox/T-001-bootstrap.md --loop bootstrap_loop --run-id bootstrap_loop-testresume` passed.
  - `python3 -m model_console run --task tasks/inbox/T-003-live-reasoning-test.md --loop live_reasoning_loop --run-id live-reasoning-001` executed with real Codex/Gemini CLIs.
- Assumptions:
  - Real model CLIs are installed/authenticated and on PATH when using non-mock loops.
  - Loop-specific eval commands in `config/loops.yaml` are customized per project.
- Residual Risks:
  - Reviewer schema compliance is brittle across vendors (example: Gemini returning prioritized_fixes as object by priority bucket).
  - Any non-empty `red_flags` currently marks a round failure, which may be too strict for iterative convergence.
