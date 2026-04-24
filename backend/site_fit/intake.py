from __future__ import annotations

from copy import deepcopy

from .models import SiteFitJob


def build_site_fit_job(
    *,
    plan: dict | None,
    structure: dict | None,
    site_constraints: dict,
    design_locks: dict | None,
    jurisdiction: str | None,
    ruleset_version: str,
) -> SiteFitJob:
    if (plan is None) == (structure is None):
        raise ValueError("Exactly one of plan or structure must be provided.")

    source_kind = "plan" if plan is not None else "structure"
    payload = deepcopy(plan if plan is not None else structure)
    return SiteFitJob(
        source_kind=source_kind,
        payload=payload,
        site_constraints=deepcopy(site_constraints or {}),
        design_locks=deepcopy(design_locks or {}),
        jurisdiction=jurisdiction,
        ruleset_version=ruleset_version,
    )

