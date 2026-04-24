from __future__ import annotations

import uuid

from ..site_fit.exporters import export_applied_plan
from ..site_fit.intake import build_site_fit_job
from ..site_fit.normalizer import normalize_plan
from ..site_fit.reporter import (
    build_compliance_summary,
    build_isolation_summary,
    build_plan_summary,
    build_registration_summary,
)
from ..site_fit.solver import propose_candidates
from ..site_fit.validator import validate_site_fit


def analyze_site_fit(req) -> dict:
    job = build_site_fit_job(
        plan=req.plan,
        structure=req.structure,
        site_constraints=req.site_constraints,
        design_locks=req.design_locks,
        jurisdiction=req.jurisdiction,
        ruleset_version=req.ruleset_version,
    )
    normalized_plan = normalize_plan(job)
    evaluation = validate_site_fit(normalized_plan, job)
    warnings = list(evaluation.warnings)
    return {
        "analysis_id": uuid.uuid4().hex[:12],
        "contract_version": req.ruleset_version,
        "status": evaluation.status,
        "isolation": build_isolation_summary(),
        "plan_summary": build_plan_summary(normalized_plan),
        "registration_summary": build_registration_summary(evaluation.registration),
        "site_summary": evaluation.site_summary,
        "compliance_summary": build_compliance_summary(evaluation),
        "warnings": warnings,
    }


def propose_site_fit(req) -> dict:
    analysis = analyze_site_fit(req)
    job = build_site_fit_job(
        plan=req.plan,
        structure=req.structure,
        site_constraints=req.site_constraints,
        design_locks=req.design_locks,
        jurisdiction=req.jurisdiction,
        ruleset_version=req.ruleset_version,
    )
    normalized_plan = normalize_plan(job)
    evaluation = validate_site_fit(normalized_plan, job)
    candidates = propose_candidates(normalized_plan, evaluation)
    return {
        **analysis,
        "candidates": candidates,
    }


def apply_site_fit(req) -> dict:
    proposal = propose_site_fit(req)
    candidate = next((item for item in proposal["candidates"] if item["candidate_id"] == req.candidate_id), None)
    if candidate is None:
        raise ValueError("Unknown site-fit candidate_id.")
    if candidate["fit_status"] != "fit_ready":
        raise ValueError("The selected candidate cannot be applied because it does not resolve fit yet.")

    job = build_site_fit_job(
        plan=req.plan,
        structure=req.structure,
        site_constraints=req.site_constraints,
        design_locks=req.design_locks,
        jurisdiction=req.jurisdiction,
        ruleset_version=req.ruleset_version,
    )
    return {
        "analysis_id": proposal["analysis_id"],
        "contract_version": req.ruleset_version,
        "candidate_id": req.candidate_id,
        "apply_status": "applied",
        "isolation": proposal["isolation"],
        "registration_summary": proposal["registration_summary"],
        "compliance_summary": proposal["compliance_summary"],
        "applied_plan": export_applied_plan(
            job,
            candidate_id=req.candidate_id,
            change_set=candidate.get("changes") or [],
        ),
        "change_set": candidate.get("changes") or [],
        "warnings": proposal["warnings"],
    }


def validate_site_fit_request(req) -> dict:
    analysis = analyze_site_fit(req)
    return analysis
