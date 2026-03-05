# Task: Convert Existing macOS Recorder PRD to Chrome Extension PRD

Read and transform this source PRD file:
- `tasks/inbox/source_prd_screen_studio_macos.md`

## Objective
Rewrite the source PRD into a complete and implementation-ready V1 PRD for a Chrome extension product.

## Required output constraints
- Output artifact path must be: `artifacts/PRD_Screen_Studio_Chrome_Extension_v1.md`
- Output artifact kind must be: `spec`
- Adapt platform assumptions from macOS desktop app to Chrome extension architecture.
- Cover Manifest V3 constraints, capture APIs, extension lifecycle/service worker limitations, permission minimization, and Chrome Web Store policy compatibility.
- Keep V1 realistic and shippable; move risky/unclear items to non-goals or post-V1.
- Include concrete acceptance criteria per major feature area.

## Definition of done
- Final artifact is a self-contained Chrome extension PRD.
- Recording model reflects browser capture realities (tab/window/desktop where appropriate).
- Editing, export, and UX choices reflect extension limitations and opportunities.
- Requirements are specific enough for engineering handoff.
