from __future__ import annotations

from .constraints import evaluate_hard_constraints
from .models import ConstraintEvaluation, NormalizedPlan, SiteFitJob


def validate_site_fit(plan: NormalizedPlan, job: SiteFitJob) -> ConstraintEvaluation:
    return evaluate_hard_constraints(plan, job)

