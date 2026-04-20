# Site Fit Bounded Context

This package is intentionally isolated from the existing parse/generate DXF pipeline.

## Boundaries

- **Allowed inputs:** already-known `plan` payloads or `structure` payloads plus `site_constraints`.
- **Forbidden dependencies:** `backend/services/parse_service.py`, `backend/services/generate_dxf_service.py`, model inference internals, and DXF generation orchestration.
- **Primary responsibility:** normalize an existing plan, evaluate buildable-site constraints, propose isolated candidates, and export a separate apply payload.

## Modules

- `contracts.py` — API request/response contracts dedicated to site-fit.
- `intake.py` — request intake and XOR validation for `plan` vs `structure`.
- `normalizer.py` — converts input payloads into a stable internal summary.
- `constraints.py` / `validator.py` — hard rule evaluation.
- `mutators.py` / `solver.py` / `scorer.py` — isolated candidate generation.
- `exporters.py` — returns applied payloads without touching the DXF pipeline.
- `reporter.py` — serializable response builders for the API layer.

## Current Scope

The scaffolding currently exposes a conservative baseline strategy (`baseline_preserved`) so the team can extend mutators and rules without risking the production parse/generate flow.

