# Task: React Loading/Error + Bundle/Performance Modernization Skill

Create one reusable skill file for migrating an old web app to a modern React stack.

## Objective
Produce an implementation-ready `SKILL.md` that another Codex instance can use during real migrations.

The skill must cover both modules:
1) Loading skeleton + error boundary template (standardized loading/error route behavior)
2) Bundle/perf hygiene (dynamic import rules, minimal client components, avoid heavy deps on critical path)

## Mandatory output rules
- Output artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_loading_perf_modernization_only/react-loading-perf-modernization/SKILL.md`
- Artifact content must be a valid skill file with YAML frontmatter and markdown body.
- YAML frontmatter must contain only:
  - `name`
  - `description`
- Use this exact skill name in frontmatter: `react-loading-perf-modernization`
- Description must clearly include trigger contexts for both modules.

## Required content in SKILL.md
- Practical migration workflow from intake -> inventory -> implementation -> verification.

### Module A: Loading skeleton + error boundary template
- Standardized route-level loading behavior:
  - skeleton placement strategy
  - layout shift avoidance conventions
  - fallback hierarchy rules (route, section, component)
- Standardized error boundary behavior:
  - recoverable vs non-recoverable error handling
  - retry and reset patterns
  - logging/observability hooks
  - user-facing copy rules and escalation behavior
- Accessibility conventions:
  - `aria-busy`, live region usage, focus management on error/retry
  - keyboard behavior parity for retry/back actions
- Include reusable template patterns for route modules and shared wrappers.

### Module B: Bundle/perf hygiene
- Dynamic import patterns and rules:
  - what to lazy-load and what must stay eagerly loaded
  - chunk boundary guidance and anti-patterns
- Client/server component boundary guidance:
  - keep client components minimal
  - push data/logic to server where possible
  - avoid unnecessary hydration costs
- Heavy dependency control:
  - critical path budget rules
  - replacement strategy for heavy libraries
  - import hygiene and tree-shaking-safe patterns
- Performance verification:
  - baseline + post-migration measurement checklist
  - thresholds and release gates
  - common regressions and quick diagnostics

## Example requirements
- Include at least one concise before/after example for each module:
  - legacy loading/error handling -> standardized skeleton + error boundary
  - monolithic imports/client-heavy page -> lazy-split + minimal client surface

## Verification requirements
- Acceptance checklist per module.
- Regression checklist (UX stability, accessibility, performance budgets).
- Pitfalls and anti-patterns section.

## Style requirements
- Keep language concise, imperative, and implementation-focused.
- Avoid generic theory.
- Output must be directly usable as `SKILL.md` without additional editing.

## Acceptance criteria
- Skill is immediately usable for migration tasks.
- Loading/error behavior is standardized and testable.
- Accessibility and keyboard behavior preservation is explicit.
- Bundle/perf rules are concrete and enforceable.
- Performance gates are practical for real codebases.
