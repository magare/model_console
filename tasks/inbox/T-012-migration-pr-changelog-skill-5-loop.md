# Task: Migration PR + Change Log Skill

You are preparing a reusable Codex skill file for migration work.

## Objective
Create one implementation-ready `SKILL.md` that helps engineers:
1) Generate high-quality migration PR descriptions
2) Build standardized per-module migration change logs for future maintainers

## Mandatory output rules
- Artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_migration_pr_changelog_only/output_skill_rounds5/migration-pr-changelog-builder/SKILL.md`
- Artifact content must be a valid Codex skill file:
  - YAML frontmatter with `name` and `description` only
  - clear Markdown body with actionable instructions
- Use this exact skill name in frontmatter: `migration-pr-changelog-builder`
- Keep the skill concise and implementation-focused.

## Required modules
1) Migration PR generator
- Define deterministic PR description sections in this exact order:
  - `What changed`
  - `Routing`
  - `Auth/RBAC`
  - `API endpoints`
  - `i18n keys`
  - `Tests`
  - `Known gaps`
- Include section-by-section rules for:
  - required inputs
  - how to summarize impact
  - evidence links/checks expected
  - when to write `N/A` vs actionable content
- Include safety checks to prevent vague PR text.

2) Change log builder
- Define a standardized migration-note format per module for long-term maintainability.
- Include required fields for each module note, such as:
  - module name
  - old behavior
  - new behavior
  - migration rationale
  - breaking changes
  - rollout/flag details
  - rollback notes
  - validation/tests
  - owner/follow-up
- Include guidance for versioning and chronological ordering.
- Include anti-drift guidance so future updates stay consistent.

## Required workflow content
- Intake -> inventory -> draft -> validate -> publish workflow.
- Rules for extracting facts from diffs, commits, tests, and configs without hallucination.
- Quality gates for completeness, technical accuracy, and reviewer usability.

## Example requirements
- Include at least one concise worked example showing:
  - an input migration diff summary
  - generated PR section output with all required headings
  - generated per-module change log entry

## Acceptance criteria
- The resulting `SKILL.md` is directly usable as a Codex skill file.
- PR generator output is deterministic and always includes all required headings in order.
- Change log format is standardized enough for future maintainers to audit migration history.
- Guidance is practical for repeated use across many migration PRs.

## Optimization target for multi-round refinement
Given this loop runs 5 rounds, continuously improve:
- clarity
- determinism of output structure
- traceability from code changes to notes
- maintainability for future engineers
