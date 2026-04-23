# Constraint Evaluation v2 + First Thin Mutator Design

## Context

`NormalizedPlan v2` is already implemented. `site_fit` now receives reduced mutable assembly data (`room_summaries`, `boundary_segments`, `wall_segments`, `openings`), but the current evaluator still reasons only over:

- `registration.scale_locked_1to1`
- `buildable_envelope.bbox_contains_plan_bbox`

And the solver still emits only `baseline_preserved`.

That means the bounded context already has the pieces, but it still lacks the decision layer that identifies which boundary is responsible for a conflict and whether a legal/technical mutation is possible.

## Problem

A real mutator without evaluator support would be blind. It would not know:

- which exterior side is overflowing
- which concrete boundary segment owns that side
- whether the boundary is movable vs protected/locked
- whether design locks block the owning room
- whether hosted openings can be rehosted
- whether shrinking would violate room minimums

At the same time, continuing to postpone mutation entirely would create architecture paralysis.

## Goal

Ship one hybrid slice that does both:

1. **Constraint Evaluation v2** — diagnose boundary-level eligibility for site-fit changes
2. **First thin mutator** — generate and apply a real, minimal shrink candidate for simple rich plan payloads

## Non-goals

This slice does **not** implement:

- arbitrary multi-boundary optimization
- non-axis-aligned geometry edits
- structure-payload mutation
- DXF regeneration / full CAD recompilation
- opening rehost graph recomputation beyond simple carried translation
- multi-candidate search or ranking heuristics

## Recommended Scope

### Evaluator scope

For registered plan vs buildable envelope:

- detect overflow by side (`north`, `south`, `east`, `west`)
- support only **single-side overflow** for mutation hints in this slice
- map the overflowing side to real exterior `boundary_segments`
- classify each impacted boundary as:
  - `eligible`
  - `blocked_protected`
  - `blocked_locked`
  - `blocked_design_lock`
  - `blocked_room_minimum`
  - `blocked_non_axis_aligned`
  - `requires_rehost`
  - `blocked_non_rehostable_opening`
- emit per-room diagnostics for affected owner rooms
- emit normalized `mutation_hints` for the solver

### Thin mutator scope

Generate one real candidate per eligible hint when all of the following are true:

- source is `plan`
- payload is rich catalog-like plan data
- exactly one overflow side exists
- impacted boundary is axis-aligned and exterior
- impacted boundary is movable / movable_with_rehost
- all owner rooms can absorb the shrink without violating min width / min height / min area
- openings on that boundary are either absent or all rehostable

Applying the candidate should mutate the copied plan payload by:

- shifting the chosen boundary inward by the required delta
- shifting its aligned wall geometry by the same delta
- shifting hosted rehostable openings by the same delta
- updating owner room bbox edges on that side
- updating `footprint_bbox`
- returning a concrete `change_set`

## Data Model Changes

### `ConstraintEvaluation`

Add rich fields so the evaluator becomes a reusable fact source for both API reporting and solver decisions:

- `boundary_diagnostics`
- `room_diagnostics`
- `mutation_hints`

### Boundary diagnostic

Represents what the evaluator decided for one concrete boundary:

- `boundary_id`
- `side`
- `axis`
- `overflow_delta`
- `status`
- `reason`
- `owner_room_ids`
- `opening_ids`
- `requires_rehost`
- `projected_fit_status`

### Room diagnostic

Represents whether the owning room can absorb the proposed shrink:

- `room_id`
- `boundary_id`
- `axis`
- `current_width`
- `current_height`
- `projected_width`
- `projected_height`
- `projected_area`
- `status`
- `reason`

### Mutation hint

A solver-ready contract for the thin mutator:

- `boundary_id`
- `side`
- `axis`
- `delta_x`
- `delta_y`
- `owner_room_ids`
- `opening_ids`
- `requires_rehost`
- `strategy`

## Candidate Strategy

Candidate id format:

- `shrink_boundary::<boundary_id>`

Candidate semantics:

- one boundary moved inward by the exact overflow amount
- one side only
- intended to fully resolve the active overflow in the supported simple case

If the evaluator reports any unsupported condition (multiple overflow sides, no eligible boundary, blocked minimums, blocked openings, non-axis-aligned edge), the solver should return no mutation candidate.

## API / Reporting Changes

Keep the existing response shape stable, but enrich `compliance_summary` so clients can inspect why a plan is blocked and whether a mutation path exists:

- `boundary_diagnostics`
- `room_diagnostics`
- `mutation_hints`

This keeps the new behavior discoverable without inventing a separate response object yet.

## Why this is the correct next step

This slice avoids both failure modes:

- **blind mutation** — moving geometry without eligibility reasoning
- **analysis paralysis** — indefinitely delaying real mutation

It gives `site_fit` its first true boundary-aware brain **and** its first real payload-changing mutator, while staying intentionally narrow and testable.