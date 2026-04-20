from __future__ import annotations

from .models import NormalizedPlan


def build_baseline_candidate(plan: NormalizedPlan) -> dict:
    return {
        "candidate_id": "baseline_preserved",
        "strategy": "preserve_existing_layout",
        "summary": f"Keep the current {plan.source_kind} unchanged while site-fit mutators are still isolated.",
        "fit_status": "fit_ready",
        "change_count": 0,
        "changes": [],
    }

