# Task: Convert Existing macOS Recorder PRD to Chrome Extension PRD

You are working on product requirements only. Rewrite the source PRD below into a complete PRD for a **Chrome extension** product.

## Objective
Create a full V1 PRD for a Chrome extension version of this product while preserving the premium output quality goals and practical MVP scope.

## Required output constraints
- Output artifact path must be: `artifacts/PRD_Screen_Studio_Chrome_Extension_v1.md`
- Output artifact kind should remain `spec`.
- Keep the PRD structure clear with sections, requirements, and acceptance criteria.
- Explicitly adapt platform assumptions from macOS desktop app to Chrome extension architecture and permissions.
- Include Chrome-extension specific constraints and tradeoffs (Manifest V3, capture APIs, service worker/background lifecycle, permission minimization, store policy compatibility).
- Keep V1 realistic and shippable; move risky items into non-goals or post-V1.
- Keep wording implementation-ready for engineering handoff.

## Source PRD (to transform)
# PRD: Premium “Screen Studio-like” macOS Screen Recorder (V1)

## 1) Product summary
Build a **local-only macOS screen recorder + lightweight editor** that produces **“ready to post”** videos with **camera-like auto-zoom**, **re-rendered cursor polish**, **cinematic motion blur**, and **beautiful framing**—without requiring users to keyframe zooms or move to a separate editor.

---

## 2) Goals and non-goals

### Goals (V1)
- Deliver the “wow” output: **auto-zoom + cursor system + motion polish + framing** as the core signature experience.
- Make edits **non-destructive** by capturing clean video + interaction metadata, then rendering effects in preview/export.
- Provide a simple timeline to **adjust/reposition auto-zoom segments** and tweak look (cursor, blur, framing).

### Non-goals (explicitly postponed)
- Captions/transcripts, keyboard shortcut overlays, typing speed-up, masks/highlights, advanced webcam layouts, share links.

---

## 3) Target users & primary use cases

### Personas
- **Indie builders / marketers**: shipping product demos for X/LinkedIn/landing pages.
- **Educators / creators**: tutorials where attention and clarity matter.
- **Internal product teams**: short feature clips for docs and release notes.

### Top use cases
1. Record a workflow → instantly get **auto-zoomed, polished** output.
2. Fix a couple zoom moments on a timeline → export.
3. Switch to **vertical** output preset for shorts/reels with minimal rework.

---

## 4) Key value proposition (what makes it “premium”)
1. **Auto-zoom feels like a camera operator** (click-driven zoom-in + smooth pan, editable on timeline).
2. **Cursor re-rendering** (smooth glide, scalable after recording, idle hide, click highlight).
3. **Motion blur** for cursor + camera motion (preview vs export quality modes).
4. **Out-of-the-box framing** (padding, rounded corners, shadow, gradient background).

---

## 5) V1 scope (must-ship requirements)

### 5.1 Recording
**Functional requirements**
- Record **display capture** (window capture optional; can be deferred if risky).
- Record system audio (optional) and/or mic (optional).
- Store a project package with:
  - `screen.mov` (raw capture, **cursor excluded**)
  - optional audio tracks
  - `events.json` (mouse timeline; keyboard optional in v1)
  - `edits.json` (zoom segments + style settings)

**Acceptance criteria**
- Recorded video plays with correct duration and doesn’t truncate on static screen moments (handle idle frames).

---

### 5.2 Auto-zoom + camera motion (core signature)
**Functional requirements**
- Automatically generate zoom segments based on click clusters.
- Timeline controls:
  - drag segment start/end
  - delete/disable
  - toggle **auto vs manual** zoom
- Export presets:
  - **16:9** (horizontal)
  - **9:16** (vertical) with recomputed zoom framing to keep interaction region visible

**Quality bar**
- No snapping; camera movement is eased and readable.

---

### 5.3 Cursor render system (core signature)
**Functional requirements**
- Capture with cursor hidden; render cursor as a separate layer.
- Cursor settings (global, post-recording):
  - size (scales cleanly)
  - smoothing strength preset(s)
  - hide when idle toggle
  - click highlight (ring/halo)

**Quality bar**
- Cursor remains sharp at 150–250% scaling (at least for default arrow in v1).

---

### 5.4 Motion blur (core signature)
**Functional requirements**
- Single motion blur slider.
- Two internal modes:
  - preview: low samples
  - export: high samples

**Risks to explicitly handle**
- Must still produce frames if capture source is idle but camera animation continues.

---

### 5.5 Framing / backgrounds (core signature)
**Functional requirements**
- Background: solid + gradient (image/wallpaper can wait).
- Controls:
  - padding
  - corner radius
  - shadow (optional inset later)

---

### 5.6 Export
**Functional requirements**
- MP4 export first (GIF can be v2).
- Presets: 1080p; optional 4K preset (if performance allows).
- Output retains sharpness and correct aspect.

**Notes**
- Export time driven mainly by FPS/resolution/format; design UI accordingly (e.g., “Fast preview export” vs “High quality”).

---

## 6) User experience (UX) requirements

### Primary flow
1. **New Recording** → pick display → record/stop.
2. Immediately open the **Editor** with:
   - preview player
   - timeline (Zoom track + Cursor track + Framing track)
   - inspector panel for settings
3. **One-click Export** (MP4) with aspect presets.

### Editor UX principles
- “Opinionated defaults”: the first render should already look premium.
- Timeline should be minimal: users adjust a few zooms, not animate everything manually.

---

## 7) Technical approach (implementation-facing)

### Architecture principle
Capture as **clean source media + interaction metadata**, and apply premium look via a **render pass** (preview + export).

### Suggested modules (V1)
- Capture: `CaptureCoordinator`, `ScreenStreamCapture`
- Input metadata: `InputEventRecorder` (mouse required; keys optional)
- Project storage: `ProjectPackage` (mov + json)
- Timeline model: `TimelineModel` with `ZoomTrack`, `CursorTrack`, `FramingTrack`
- Rendering: `EffectGraphRenderer` applying:
  - camera transform
  - cursor layer
  - motion blur
  - framing

### Performance requirements
- Preview must be real-time and responsive:
  - allow half-res rendering
  - reduced blur samples while scrubbing

---

## 8) Metrics / success criteria
**Activation**
- % users who export a video within first session
- Time-to-first-export

**Quality proxy**
- % exports using default settings (defaults are “good enough”)
- Export failure rate / corrupted duration rate (near zero)

**Engagement**
- Average number of zoom edits per project (should be low)
- Repeat usage: recordings per user per week

---

## 9) Risks and mitigations
- **Idle frames / static screen breaks duration or camera animation**
  - Mitigation: renderer advances time even if captured surface doesn’t change.
- **Motion blur makes text unreadable**
  - Mitigation: conservative default blur; clamp slider; preview/export modes.
- **Scope creep from nice-to-haves**
  - Mitigation: enforce v1 boundary (no captions/shortcuts/typing speedups/masks/webcam).

---

## 10) Milestones (suggested)
1. MVP Capture + Project Packaging  
2. Auto-zoom generation + basic timeline editing  
3. Cursor layer (smooth + scalable + clicks)  
4. Framing (padding/corners/shadow/gradient)  
5. Motion blur (preview/export modes)  
6. Export presets (16:9 + 9:16) + reliability hardening  
7. Beta polish (defaults, edge cases)

## Definition of done
- Final artifact is a self-contained Chrome extension PRD (not a desktop PRD with minor edits).
- Recording model reflects browser tab/window/desktop capture realities.
- Export, editing, and UX constraints match extension limitations and opportunities.
- Acceptance criteria are concrete and testable.
