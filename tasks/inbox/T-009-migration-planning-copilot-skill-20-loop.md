# Task: Migration Planning + Sequencing Skill for GitHub Copilot

You are preparing a reusable skill/prompt pack for GitHub Copilot Chat.

## Objective
Create an implementation-ready migration planning and sequencing skill that helps engineers migrate an old app to a new app.

The skill must include two core modules:
1) Module migration planner: given "old stack -> new stack", produce a phased plan with this sequence:
   - inventory
   - scaffold
   - rewrite
   - hard parts
   - quality
2) Risk & dependency mapper: identify likely migration risks and dependencies across:
   - routing
   - auth
   - data fetching
   - i18n
   - styling
   - state
   - storage
   and propose mitigations.

## Mandatory output rules
- Output artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_migration_planning_only/migration-planning-sequencing-copilot-skill.md`
- Artifact content must be directly copyable into GitHub Copilot resources.
- Provide one clear primary prompt that can run in Copilot Chat and produce deterministic, structured outputs.
- Include explicit input contract (what user provides) and explicit output contract (what Copilot must return).
- Include checklists for sequencing, dependencies, and rollout safety.
- Include a concrete risk matrix template (risk, impact, likelihood, owner, mitigation, fallback, validation).
- Include phase-by-phase deliverables and entry/exit criteria.
- Include cutover strategy guidance (parallel run, feature flags, rollback, observability gates).
- Include at least one full worked example:
  old stack -> new stack, then output both module plan + risk/dependency mapping.
- Keep language concise and implementation-focused.

## Acceptance criteria
- The skill is immediately usable in GitHub Copilot without extra explanation.
- The skill outputs both modules in one run and enforces sequencing discipline.
- Risks and dependencies are mapped explicitly with mitigations and ownership.
- The output is copyable and organized for engineers.

## Additional optimization target
Given this loop runs many rounds, continuously improve for:
- clarity,
- missing edge cases,
- migration safety,
- realistic sequencing,
- practical execution details.
