# Task: React Migration Modernization Skill

Create one reusable skill file for migrating an old web app to a modern React stack.

## Objective
Produce an implementation-ready `SKILL.md` that another Codex instance can use during real migrations.

The skill must cover all three modules:
1) Web components -> React components mapping
2) Form stack modernization (`react-hook-form` + schema validation in a zod-like style)
3) Table/grid modernization (headless table in a tanstack-like style + standardized `DataTable`)

## Mandatory output rules
- Output artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_react_migration_modernization_only/react-modernization-migration/SKILL.md`
- Artifact content must be a valid skill file with YAML frontmatter and markdown body.
- YAML frontmatter must contain only:
  - `name`
  - `description`
- Use this exact skill name in frontmatter: `react-modernization-migration`
- Description must clearly include trigger contexts for all three modules.

## Required content in SKILL.md
- Practical migration workflow from intake -> inventory -> implementation -> verification.
- Web components -> React mapping guidance:
  - custom element to React component replacement rules
  - slot/content projection mapping to `children` and named render props
  - event mapping (`CustomEvent`) to React handler props
  - attribute/property mapping and controlled/uncontrolled state handling
  - accessibility and keyboard behavior parity (roles, aria attrs, focus order, key handling)
- Form modernization guidance:
  - `react-hook-form` architecture patterns
  - schema-driven validation patterns (zod-like)
  - field-level, form-level, and async validation conventions
  - standardized error display and accessibility conventions (`aria-invalid`, `aria-describedby`, live region summary)
  - migration sequence from legacy handlers to RHF controllers/register
- Table/grid modernization guidance:
  - headless table modeling (columns, sorting, filtering, pagination, row selection, column visibility)
  - standardized `DataTable` wrapper contract (props, extension points, states)
  - server-side vs client-side data operations strategy
  - keyboard and screen-reader behavior parity for tabular UIs
  - performance guidance (memoization, virtualization thresholds)
- Verification sections:
  - acceptance checklist per module
  - regression checklist for accessibility + keyboard
  - common pitfalls and anti-patterns

## Example requirements
- Include at least one concise before/after example for each module:
  - custom element -> React
  - legacy form -> RHF + schema
  - legacy grid -> headless table + `DataTable`

## Style requirements
- Keep language concise, imperative, and implementation-focused.
- Avoid generic theory.
- Output must be directly usable as `SKILL.md` without additional editing.

## Acceptance criteria
- Skill is immediately usable for migration tasks.
- All three modules are covered with concrete, repeatable patterns.
- Accessibility and keyboard behavior preservation is explicit and testable.
- Error handling and validation conventions are standardized.
- Data table modernization path is practical for real codebases.
