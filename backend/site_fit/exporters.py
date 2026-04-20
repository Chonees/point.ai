from __future__ import annotations

from copy import deepcopy

from .models import SiteFitIsolation, SiteFitJob


def export_applied_plan(job: SiteFitJob, *, candidate_id: str) -> dict:
    return {
        job.source_kind: deepcopy(job.payload),
        "site_fit_meta": {
            "pipeline": SiteFitIsolation().pipeline,
            "candidate_id": candidate_id,
            "ruleset_version": job.ruleset_version,
        },
    }

