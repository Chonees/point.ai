# Site Fit Buildable Polygon Honesty Design

## Context

`site_fit` now has `Constraint Evaluation v2` plus a first thin mutator. The remaining known debt is that `buildable_polygon` still gets collapsed to its bounding box inside `backend/site_fit/constraints.py`, which can produce false `fit_ready` results for non-rectangular sites.

## Problem

Today, a plan can pass site-fit validation when its footprint bbox lies inside the polygon's enclosing rectangle even if the actual footprint spills outside the real polygon.

That is dishonest behavior. The bounded context should either evaluate polygon fit truthfully or explicitly refuse to claim fit.

## Goal

Make `site_fit` evaluate `buildable_polygon` honestly for the current geometry level.

## Recommended approach

Implement real containment for the normalized **footprint rectangle**:

- normalize `buildable_polygon` into canonical units
- derive the rectangle edges/corners from `plan.footprint_bbox`
- require all rectangle corners to be inside/on the polygon
- require no rectangle edge to cross a polygon edge
- if `buildable_envelope` also exists, both checks must pass

## Non-goals

This slice does not:

- add mutator behavior for polygon conflicts
- perform arbitrary polygon clipping
- evaluate room-by-room or boundary-by-boundary fit against polygon interiors
- solve holes/multipolygon support

## Expected behavior

- polygon-only constraints can now produce truthful `fit_ready` / `buildable_conflict`
- envelope + polygon constraints act as an AND gate
- polygon conflicts report a dedicated rule id and violation payload
- polygon conflicts do not emit mutation hints in this slice

## Why this is the right next step

It removes the last known dishonest success path in `site_fit` without expanding the mutator beyond its current narrow scope.