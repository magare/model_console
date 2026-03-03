You are advising improvements to this repository: `model_counsel` (`mc` CLI).

Project context:
- This is a local-first orchestration runner for iterative IMPLEMENTER/REVIEWER loops.
- Loops are configured in `config/loops.yaml` with round limits, score thresholds, and swap behavior.
- Agents are configured in `config/agents.yaml` and can be Codex/Gemini/Claude (or mocks).
- Prompts are template-driven (`prompts/implementer.template.txt`, `prompts/reviewer.template.txt`).
- Outputs are strict JSON validated by schemas in `schemas/`.
- Runs persist state, logs, round artifacts, and reports under `runs/<run_id>/`.
- Current usage works well for single, small tasks where one prompt leads to one concise output.

Current pain point:
- We want stronger performance on complex tasks with multiple dependent subproblems where each step depends on previous outputs.
- Today, users often provide one short request, get one answer, and then manually continue.
- We need a strategy so the model council itself handles multi-step dependency management more effectively.

User question (exact):
"I basically want to improve this model's counsel by asking the model's counsel itself. For example, currently we are giving one short thing to the model counsel, and it is giving me some response. That is good for singular tasks, but what if I want to do a complex task which has multiple things inside it, and one thing is based upon the previous one? In that case, I want to have some strategy in which the model can be effective."

What to produce:
- A concrete strategy for complex, dependency-heavy tasks in this system.
- Specific recommended changes to:
  - task format
  - loop configuration
  - prompt templates
  - schemas/artifacts
  - stopping and resume behavior
- A phased rollout plan (small first step, medium step, full step).
- Risks/tradeoffs and how to measure improvement.
