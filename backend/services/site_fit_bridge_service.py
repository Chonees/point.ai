import json
from pathlib import Path

from ..services.cad_workspace_service import extract_cad_workspace
from ..services.site_fit_service import apply_site_fit, propose_site_fit
from ..site_fit.contracts import SiteFitAnalyzeRequest, SiteFitApplyRequest


CATALOG_PLAN_ID = "seminole-2000"
CATALOG_PLAN_NAME = "SEMINOLE2000"
CATALOG_PLAN_PATH = Path(__file__).resolve().parents[1] / "site_fit_bridge" / "assets" / "seminole-2000.plan.json"


def load_mvp_catalog_plan() -> dict:
    payload = json.loads(CATALOG_PLAN_PATH.read_text(encoding="utf-8"))
    payload["unit"] = payload.get("unit") or payload.get("canonical_unit") or "inch"
    payload["name"] = payload.get("name") or CATALOG_PLAN_NAME
    return payload


def build_mvp_site_constraints(cad_analysis: dict, plan_payload: dict) -> tuple[dict, list[str]]:
    fit = cad_analysis.get("fit_summary") or {}
    buildable_bbox = fit.get("buildable_bbox")
    if not buildable_bbox:
        raise ValueError("Bridge MVP v1 needs an extracted buildable bbox.")

    plan_bbox = plan_payload.get("footprint_bbox") or {}
    return {
        "unit": cad_analysis.get("canonical_unit") or "inch",
        "placed_plan_footprint": {
            "x": buildable_bbox["x1"],
            "y": buildable_bbox["y1"],
            "width": plan_bbox["width"],
            "height": plan_bbox["height"],
        },
        "buildable_envelope": {
            "x": buildable_bbox["x1"],
            "y": buildable_bbox["y1"],
            "width": buildable_bbox["width"],
            "height": buildable_bbox["height"],
        },
        "buildable_polygon": fit.get("buildable_polygon") or [],
    }, [
        "Bridge MVP v1 anchors SEMINOLE2000 at the buildable bbox origin for a fixed 1:1 registration lane.",
    ]


def propose_mvp_site_fit(*, filename: str, data: bytes) -> dict:
    cad_analysis = extract_cad_workspace(filename=filename, data=data)
    plan_payload = load_mvp_catalog_plan()
    site_constraints, warnings = build_mvp_site_constraints(cad_analysis, plan_payload)
    proposal = propose_site_fit(
        SiteFitAnalyzeRequest(
            plan=plan_payload,
            site_constraints=site_constraints,
        )
    )
    return {
        "plan_id": CATALOG_PLAN_ID,
        "plan_name": plan_payload["name"],
        "cad_analysis": cad_analysis,
        "site_constraints": site_constraints,
        "proposal": proposal,
        "warnings": warnings + list(cad_analysis.get("warnings") or []),
    }


def apply_mvp_site_fit(req) -> dict:
    if req.plan_id != CATALOG_PLAN_ID:
        raise ValueError("Bridge MVP v1 only supports SEMINOLE2000.")

    plan_payload = load_mvp_catalog_plan()
    applied = apply_site_fit(
        SiteFitApplyRequest(
            plan=plan_payload,
            site_constraints=req.site_constraints,
            candidate_id=req.candidate_id,
        )
    )
    return {
        "plan_id": CATALOG_PLAN_ID,
        "plan_name": plan_payload["name"],
        "apply": applied,
        "warnings": [
            "Bridge MVP v1 is a fixed SEMINOLE2000 lane and does not generalize catalog selection yet.",
        ],
    }
