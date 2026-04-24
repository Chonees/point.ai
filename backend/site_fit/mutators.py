from __future__ import annotations

from .models import MutationHint, NormalizedPlan


def build_baseline_candidate(plan: NormalizedPlan) -> dict:
    return {
        "candidate_id": "baseline_preserved",
        "strategy": "preserve_existing_layout",
        "summary": f"Keep the current {plan.source_kind} unchanged while site-fit mutators are still isolated.",
        "fit_status": "fit_ready",
        "change_count": 0,
        "changes": [],
    }


def build_shrink_boundary_candidate(plan: NormalizedPlan, hint: MutationHint) -> dict:
    delta_x = float(hint.delta_x)
    delta_y = float(hint.delta_y)
    return {
        "candidate_id": f"shrink_boundary::{hint.boundary_id}",
        "strategy": "shrink_boundary",
        "summary": f"Move boundary {hint.boundary_id} inward to resolve {hint.side} overflow.",
        "fit_status": "fit_ready",
        "change_count": 1,
        "changes": [
            {
                "boundary_id": hint.boundary_id,
                "side": hint.side,
                "delta_x": delta_x,
                "delta_y": delta_y,
                "owner_room_ids": list(hint.owner_room_ids),
                "opening_ids": list(hint.opening_ids),
                "requires_rehost": hint.requires_rehost,
            }
        ],
    }

