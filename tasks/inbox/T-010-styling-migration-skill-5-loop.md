# Task: Styling Migration Skill (SCSS -> Utility CSS + Tokens + Variants)

You are preparing a reusable Codex skill file for migration work.

## Objective
Create one implementation-ready `SKILL.md` that helps engineers migrate styling from legacy SCSS/component styles to utility-first CSS (Tailwind-style), while enforcing design tokens and a consistent variant system.

The skill must include these three modules:
1) SCSS -> utility CSS migration rules
   - Translate layout, spacing, typography, and interaction states into utility classes.
   - Include deterministic mapping rules for common patterns (container/layout, margin/padding, font/line-height, hover/focus/disabled/error states, responsive breakpoints).
2) Design token enforcement
   - Explicitly enforce: no hardcoded colors.
   - Use semantic tokens and define fallback/token-mapping rules for unknown legacy values.
   - Include theme and dark-mode readiness checks.
3) Variant system rules
   - Define a generic CVA-like approach for `size`, `intent`, and `state` variants.
   - Include `cn()` composition rules and conflict-resolution order.
   - Include guidance for default variants and extending variants safely.

## Mandatory output rules
- Artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_styling_migration_only/output_skill_rounds5/styling-migration-system/SKILL.md`
- Artifact content must be a valid Codex skill file:
  - YAML frontmatter with `name` and `description` only
  - clear Markdown body with actionable instructions
- Keep the skill concise and implementation-focused.
- Include at least one worked example showing:
  - legacy SCSS/component style snippet
  - migrated utility class output
  - token usage
  - variant usage (CVA-like + `cn()`)
- Include a short validation checklist for post-migration review.

## Acceptance criteria
- The resulting `SKILL.md` is directly usable as a Codex skill file.
- All three modules are present and practical for real migrations.
- Rules are deterministic enough to reduce style drift across teams.
- The skill is optimized for repeated use in migration tasks.

## Optimization target for multi-round refinement
Given this loop runs 5 rounds, continuously improve:
- clarity
- deterministic mapping detail
- migration safety and guardrails
- edge-case handling for states/responsiveness/themes
