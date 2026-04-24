# Bridge MVP v1 Design

## Context

Point.ai already has the main technical pieces in place, but they still live in parallel tracks:

- curated floor-plan truth for `SEMINOLE2000`
- runtime CAD extraction through `cad_workspace`
- isolated `site_fit` analyze / propose / apply endpoints
- chat-first shell with inline CAD review

The current product gap is not branch drift anymore. The current gap is orchestration.

Today the chat tool can:

- accept an uploaded image and generate a DXF-oriented floor-plan result
- accept an uploaded `.dxf` / `.dwg` and run CAD review through `/api/cad-workspace/extract`

But it still cannot execute the MVP flow described in `MVP.md`:

> upload a site plan, choose a curated catalog floor plan, analyze fit, propose an adjustment, approve it, and continue toward a final DXF.

## Problem

The repo does not yet connect:

1. **runtime site plan upload**
2. **curated catalog floor plan selection**
3. **`site_fit/propose` and `site_fit/apply`**
4. **chat human-in-the-loop approval**

Without that bridge, we can keep improving internals forever and still not run a real MVP test.

## Goal

Ship one narrow but honest bridge slice that enables the first real MVP test lane:

- fixed curated floor plan: `SEMINOLE2000`
- uploaded runtime site plan: one `.dxf` / `.dwg`
- extracted site constraints feed `site_fit`
- chat can show fit verdict + proposal summary
- chat can apply one supported candidate

This slice is about **product flow validation**, not final system completeness.

## Non-goals

This slice does **not** implement:

- multi-plan catalog browsing
- arbitrary catalog plan selection UX
- final production-grade DXF reconstruction/export
- broad extractor generalization for every site-plan drafting style
- new mutator families beyond the current thin mutator
- full `footprint_polygon` truth inside `site_fit`

## Decision

Choose a **controlled first MVP lane** instead of chasing broad generality first.

The bridge will support:

- one curated plan (`SEMINOLE2000`)
- one uploaded site plan at runtime
- existing `site_fit` bounded context
- human approval in chat

This is the shortest path to a meaningful first MVP test without architectural cheating.

## Design

### 1. Fixed catalog resolver for MVP lane

Add a minimal runtime resolver for the curated `SEMINOLE2000` plan.

The resolver should:

- load the canonical curated payload for `SEMINOLE2000`
- return a `plan` shape that `site_fit` already understands
- stay explicit that this is a temporary MVP lane, not the final catalog system

This keeps the floor-plan side stable while we validate the runtime site-plan side.

### 2. Site-plan extraction becomes upstream evidence only

For this slice, `cad_workspace/extract` should be used as the runtime site-plan evidence source.

We only need enough extracted truth to build the first `site_fit` request:

- `buildable_bbox`
- `buildable_polygon` when available
- canonical unit

The bridge should not pretend the uploaded CAD file contains the catalog floor plan. The curated plan and the runtime site plan are separate inputs in the MVP flow.

### 3. Backend bridge service

Add one thin orchestration layer that:

1. receives a runtime site-plan upload plus a fixed plan choice (`SEMINOLE2000`)
2. extracts site constraints from CAD
3. loads the curated catalog payload
4. calls `site_fit/analyze` and `site_fit/propose`
5. returns a chat-safe summary contract

The bridge should preserve the existing bounded contexts:

- `cad_workspace` extracts
- `site_fit` reasons
- chat consumes the result

No new geometry engine should be introduced here.

### 4. Chat HITL v1

The chat shell should gain one narrow MVP artifact/action flow:

- user uploads a site plan CAD file
- user asks to fit `SEMINOLE2000`
- assistant returns:
  - fit verdict
  - candidate summary
  - inline review artifact
  - explicit apply action for the supported candidate

This does **not** need full conversational re-planning yet. It only needs one honest candidate/apply loop.

### 5. Apply path stays narrow and truthful

When the candidate is applied:

- use the existing `site_fit/apply` result
- surface the mutated payload / summary in chat
- keep the response explicit about current limitations

This slice can end with a truthful applied-result artifact even if the final DXF export remains the next slice.

## Testing strategy

### Mandatory test lane

Build one controlled first MVP test around:

- curated plan: `SEMINOLE2000`
- one known-good site plan fixture
- one supported overflow case that current thin mutator can resolve

### Required automated checks

1. backend bridge test:
   - runtime site plan extraction feeds a valid `site_fit/propose`
2. chat integration test:
   - upload CAD → assistant returns fit/proposal artifact
3. apply integration test:
   - assistant can apply the supported candidate and return the updated result

### Manual test definition

The first honest manual MVP test is:

1. open a new thread
2. upload a known-good site plan DXF
3. ask to fit `SEMINOLE2000`
4. see fit verdict + proposal summary
5. apply the proposal
6. confirm the result remains coherent and honest

That counts as the first MVP test lane, even before final DXF export is added.

## Risks

1. **CAD extraction contract mismatch**
   - extracted site constraints may need a small adapter before they can feed `site_fit` cleanly

2. **Chat artifact model too narrow**
   - current thread artifacts may need one more kind for site-fit proposal/apply state

3. **MVP lane confusion**
   - if we do not label this as a controlled `SEMINOLE2000` lane, the product may appear more general than it really is

## Success criteria

This slice is successful if:

- a user can upload one site plan CAD file in chat
- Point.ai can run a real `SEMINOLE2000` fit analysis against it
- Point.ai can return a proposal from `site_fit`
- the user can apply that proposal inside the chat loop
- the flow is honest about current narrow scope

## Why this is the right next step

The current system no longer needs another abstract capability win before proving product flow.

What it needs is one real, narrow, end-to-end lane.

Bridge MVP v1 is that lane.
