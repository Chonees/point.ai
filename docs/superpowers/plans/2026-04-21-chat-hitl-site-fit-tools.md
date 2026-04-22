# Chat HITL Site-Fit Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add both chat-first site-fit tools: truthful fit review from CAD analysis and guided human-in-the-loop adjustment candidates/apply actions.

**Architecture:** Keep `backend/site_fit/` isolated and extend it with the first real candidate/apply path for simple room-boundary shrink proposals. In the frontend chat shell, preserve honesty: CAD upload performs fit review, artifact actions trigger guided adjustment proposal/apply, and the chat transcript remains the human approval surface.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, pytest, React, TypeScript, Vitest.

---

## File Map

- Modify: `backend/site_fit/mutators.py`
- Modify: `backend/site_fit/scorer.py`
- Modify: `backend/site_fit/solver.py`
- Modify: `backend/site_fit/exporters.py`
- Modify: `backend/services/site_fit_service.py`
- Modify: `tests/test_site_fit_api.py`
- Modify: `frontend/src/features/siteFit/types.ts`
- Modify: `frontend/src/features/chatThread/thread.types.ts`
- Modify: `frontend/src/features/chatThread/chatAgent.ts`
- Modify: `frontend/src/features/chatThread/chatAgent.test.ts`
- Modify: `frontend/src/features/chatThread/components/ArtifactCard.tsx`
- Modify: `frontend/src/features/chatThread/components/ThreadMessageList.tsx`
- Modify: `frontend/src/features/chatThread/ThreadWorkspacePage.tsx`
- Modify: `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

## Task 1: Add the first real guided-adjustment candidate/apply path in backend

**Files:**
- Modify: `tests/test_site_fit_api.py`
- Modify: `backend/site_fit/mutators.py`
- Modify: `backend/site_fit/solver.py`
- Modify: `backend/site_fit/scorer.py`
- Modify: `backend/site_fit/exporters.py`
- Modify: `backend/services/site_fit_service.py`

- [ ] Write failing API tests for propose/apply when a plan overflows but an unlocked boundary room can shrink to fit.
- [ ] Run the isolated backend site-fit tests and verify the new expectations fail for the missing candidate/apply path.
- [ ] Implement minimal boundary-room shrink mutators that produce explicit `changes` with axis, room name, and delta inches.
- [ ] Implement apply/export so the selected candidate returns a mutated `plan` plus non-empty `change_set`.
- [ ] Re-run `tests/test_site_fit_api.py` and confirm green.

## Task 2: Teach the chat agent to run both tools with thread context

**Files:**
- Modify: `frontend/src/features/siteFit/types.ts`
- Modify: `frontend/src/features/chatThread/thread.types.ts`
- Modify: `frontend/src/features/chatThread/chatAgent.ts`
- Modify: `frontend/src/features/chatThread/chatAgent.test.ts`

- [ ] Write failing chat-agent tests for CAD fit review artifacts and guided adjustment proposal/apply prompts.
- [ ] Run the focused Vitest spec and verify the new chat tests fail for missing actions/context.
- [ ] Extend chat tool types so artifacts can carry action buttons and the agent can return thread-context updates.
- [ ] Implement CAD review output that says the truth, stores the latest CAD analysis in context, and exposes `Probar ajuste guiado` when relevant.
- [ ] Implement guided adjustment proposal/apply commands that translate the latest CAD analysis into `site_fit` requests and surface candidates as chat artifacts.
- [ ] Re-run the focused chat-agent Vitest spec and confirm green.

## Task 3: Wire artifact actions through the chat shell

**Files:**
- Modify: `frontend/src/features/chatThread/components/ArtifactCard.tsx`
- Modify: `frontend/src/features/chatThread/components/ThreadMessageList.tsx`
- Modify: `frontend/src/features/chatThread/ThreadWorkspacePage.tsx`
- Modify: `frontend/src/features/chatThread/ThreadWorkspacePage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] Write failing UI tests proving artifact action buttons render and route back through the chat transcript.
- [ ] Run the focused frontend specs and verify they fail for the missing action wiring.
- [ ] Implement artifact action callbacks from card -> message list -> thread workspace -> app.
- [ ] Store per-thread chat tool context in `App.tsx` so guided adjustment can use the latest CAD analysis/proposal.
- [ ] Re-run the focused App/thread tests and confirm green.

## Task 4: Verify the whole slice end-to-end at the focused test level

**Files:**
- No new files

- [ ] Run `python -m pytest tests/test_site_fit_api.py -q`.
- [ ] Run `npm --prefix frontend test -- src/features/chatThread/chatAgent.test.ts src/features/chatThread/ThreadWorkspacePage.test.tsx src/App.test.tsx`.
- [ ] Confirm both commands pass and only then report completion.
