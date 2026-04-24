# Site-fit unit normalization + UI review plan

## Goal
- Normalize mixed CAD units into a single internal measurement space before site-fit registration.
- Expose a minimal, isolated UI panel that can analyze a Dawson-based manual fixture through `/api/v2/site-fit/analyze`.

## Constraints
- Do not modify the existing generate-dxf pipeline behavior.
- Keep `site_fit` as a bounded context with separate contracts.
- Do not build the frontend.

## Backend slice
1. Add CAD unit conversion helpers for physical AutoCAD units.
2. Normalize `plan` / `structure` footprint bboxes into inches.
3. Normalize site bboxes (`placed_plan_footprint`, `buildable_envelope`, `buildable_polygon`) into inches before registration and fit checks.
4. Preserve the existing scale-locked `1.0` behavior after normalization.

## Frontend slice
1. Add a `siteFit` feature folder with:
   - manual Dawson fixtures
   - isolated analyze hook
   - review panel component
2. Mount the panel inside `UploadPanel` as a separate section.
3. Show:
   - selected case
   - source note
   - backend registration status
   - fit status / warnings / violations

## Verification
- Backend: `pytest tests/test_site_fit_api.py tests/test_v2_api.py -q`
- Frontend: `npm --prefix frontend test -- src/features/siteFit/useSiteFitReview.test.ts src/features/siteFit/SiteFitReviewPanel.test.tsx`
