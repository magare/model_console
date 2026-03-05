# Task: State Management Migration Skill (Legacy Store/Event-Bus -> React State)

Create one reusable skill file for migrating legacy client-side state patterns to modern React state architecture.

## Objective
Produce an implementation-ready `SKILL.md` that another Codex instance can use during real migrations from:
- legacy global store patterns
- event-bus-heavy UIs
to:
- React local/component state
- Context + reducer patterns
- URL state
- server cache patterns

## Mandatory output rules
- Output artifact kind must be: `spec`
- Output artifact path must be exactly:
  `artifacts/output_skill_state_management_migration_only/output_skill_rounds5/state-management-migration-react-skill.md`
- Artifact content must be a valid skill file with YAML frontmatter and markdown body.
- YAML frontmatter must contain only:
  - `name`
  - `description`
- Use this exact skill name in frontmatter: `state-management-migration-react`
- Description must clearly include trigger contexts for:
  - legacy store to React migration
  - event bus replacement/refactoring
  - React state placement decisions

## Required content in skill file
- Practical migration workflow from intake -> inventory -> state placement -> incremental rewrite -> verification.
- Decision framework for choosing state location:
  - local/component state
  - context state
  - URL/search-param state
  - server cache state
- A deterministic decision tree with concrete criteria:
  - ownership, lifetime, share scope, persistence, SSR/deep-link needs, staleness/invalidations, write frequency.
- Legacy store/event-bus migration guidance:
  - mapping legacy store slices/actions/subscriptions to React patterns
  - replacing pub/sub events with explicit props, context actions, or domain hooks
  - adapter/strangler strategy for incremental migration
  - decommissioning plan for old store and bus
- “How to unwind event listeners safely” section that includes:
  - listener inventory and ownership tracing
  - safe unsubscribe patterns
  - `useEffect` cleanup and idempotency guidance
  - `AbortController`/cancellation usage where applicable
  - StrictMode double-invocation resilience
  - leak/race-condition checks and rollback path
- Verification sections:
  - acceptance checklist for state placement and behavior parity
  - regression checklist for stale data, race conditions, and listener leaks
  - common pitfalls and anti-patterns

## Example requirements
- Include concise before/after examples for:
  - event-bus listener flow -> React hook/context flow
  - legacy global store slice -> chosen React state placement

## Style requirements
- Keep language concise, imperative, and implementation-focused.
- Avoid generic theory.
- Keep final artifact under 700 words.
- Output must be directly usable as a skill file without additional editing.

## Acceptance criteria
- Skill is immediately usable for migration tasks.
- Decision tree is concrete enough to choose between local/context/URL/server cache state.
- Event listener unwind guidance is explicit, safe, and testable.
- Migration path is practical for incremental adoption in real codebases.
