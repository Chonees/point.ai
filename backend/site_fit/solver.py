from __future__ import annotations

from .models import ConstraintEvaluation, NormalizedPlan
from .mutators import build_baseline_candidate
from .scorer import score_candidate


def propose_candidates(plan: NormalizedPlan, evaluation: ConstraintEvaluation) -> list[dict]:
    if evaluation.status != "fit_ready":
        return []
    return [score_candidate(build_baseline_candidate(plan))]

