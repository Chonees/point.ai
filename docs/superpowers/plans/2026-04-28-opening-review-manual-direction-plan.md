# Opening Review Direct Manipulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Opening Review feel direct and predictable by drawing DXF-like symbols and separating selection, movement, and direction choice into different on-canvas interactions.

**Architecture:** Keep the backend rollback intact and concentrate the improvement in the Desktop review layer. Push symbol geometry into pure helpers so the SVG renderer and the tests share the same truth.

**Tech Stack:** React 19, TypeScript, SVG overlays, Vitest, Testing Library.

---

### Task 1: Lock the new UX with failing tests

**Files:**
- Modify: `frontend/src/features/workspace/openingsReview.test.ts`
- Modify: `frontend/src/features/workspace/OpeningsReviewCanvas.test.tsx`

- [ ] **Step 1: Add failing helper tests for move-handle center and DXF-like door/window preview geometry**
- [ ] **Step 2: Add failing component tests for select-only, move-only-from-handle, and swing-target interaction**
- [ ] **Step 3: Run focused Vitest and confirm the direct-manipulation behavior does not exist yet**

### Task 2: Implement shared review geometry helpers

**Files:**
- Modify: `frontend/src/features/workspace/openingsReview.ts`

- [ ] **Step 1: Add pure helpers for move-handle center and swing target points**
- [ ] **Step 2: Add pure DXF-like preview geometry builders for doors and windows**
- [ ] **Step 3: Keep the existing review serialization helpers intact**

### Task 3: Rebuild the review canvas interaction model

**Files:**
- Modify: `frontend/src/features/workspace/OpeningsReviewCanvas.tsx`

- [ ] **Step 1: Make body click only select the opening**
- [ ] **Step 2: Move dragging to a dedicated central move handle**
- [ ] **Step 3: Replace external direction buttons with on-symbol swing targets**
- [ ] **Step 4: Render selected openings as DXF-like previews with current/alternate variants**
- [ ] **Step 5: Re-run focused Vitest and confirm green**

### Task 4: Verify the session workflow still holds

**Files:**
- Verify only

- [ ] **Step 1: Run `useGenerateDxf` review-session tests together with the canvas/helper tests**
- [ ] **Step 2: Inspect `git diff` and confirm only frontend review UX files changed**
