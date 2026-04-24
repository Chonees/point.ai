from __future__ import annotations

from .models import ConstraintEvaluation, NormalizedPlan
from .mutators import build_baseline_candidate, build_shrink_boundary_candidate
from .scorer import score_candidate


def propose_candidates(plan: NormalizedPlan, evaluation: ConstraintEvaluation) -> list[dict]:
    if evaluation.status == "fit_ready":
        return [score_candidate(build_baseline_candidate(plan))]
    if evaluation.status != "buildable_conflict":
        return []
    if plan.source_kind != "plan":
        return []
    return [
        score_candidate(build_shrink_boundary_candidate(plan, hint))
        for hint in evaluation.mutation_hints
    ]

