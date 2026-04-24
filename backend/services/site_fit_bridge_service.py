import json
import tempfile
import uuid
from pathlib import Path

from ..site_fit_bridge.exporter import export_bridge_apply_dxf
from ..services.cad_workspace_service import extract_cad_workspace
from ..services.site_fit_service import apply_site_fit, propose_site_fit
from ..site_fit.contracts import SiteFitAnalyzeRequest, SiteFitApplyRequest


CATALOG_PLAN_ID = "seminole-2000"
CATALOG_PLAN_NAME = "SEMINOLE2000"
CATALOG_PLAN_PATH = Path(__file__).resolve().parents[1] / "site_fit_bridge" / "assets" / "seminole-2000.plan.json"
CAD_WORKSPACE_DIR = Path(tempfile.gettempdir()) / "pointai_cad_workspace"
BRIDGE_APPLY_DIR = Path(tempfile.gettempdir()) / "pointai_site_fit_bridge"
BRIDGE_APPLY_DIR.mkdir(exist_ok=True)


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

    cad_analysis = _load_cad_analysis_snapshot(req.cad_analysis_id)
    plan_payload = load_mvp_catalog_plan()
    applied = apply_site_fit(
        SiteFitApplyRequest(
            plan=plan_payload,
            site_constraints=req.site_constraints,
            candidate_id=req.candidate_id,
        )
    )
    apply_id = uuid.uuid4().hex[:12]
    export_url = f"/api/v2/site-fit/bridge/export/{apply_id}"
    snapshot = {
        "apply_id": apply_id,
        "pipeline": "site_fit_bridge_mvp_v1",
        "scope": "seminole-2000-only",
        "plan_id": CATALOG_PLAN_ID,
        "plan_name": plan_payload["name"],
        "cad_analysis_id": req.cad_analysis_id,
        "cad_analysis": cad_analysis,
        "apply": applied,
        "warnings": [
            "Bridge MVP v1 is a fixed SEMINOLE2000 lane and does not generalize catalog selection yet.",
        ],
    }
    _save_apply_snapshot(snapshot)
    return {
        "apply_id": apply_id,
        "export_url": export_url,
        "plan_id": CATALOG_PLAN_ID,
        "plan_name": plan_payload["name"],
        "apply": applied,
        "warnings": list(snapshot["warnings"]),
    }


def export_bridge_apply_snapshot(*, apply_id: str) -> tuple[Path, str]:
    snapshot = _load_apply_snapshot(apply_id)
    output_name = f"{apply_id}-bridge-apply.dxf"
    output_path = BRIDGE_APPLY_DIR / output_name
    export_bridge_apply_dxf(snapshot, output_path)
    return output_path, output_name


def _load_cad_analysis_snapshot(cad_analysis_id: str) -> dict:
    analysis_id = str(cad_analysis_id or "").strip()
    if not analysis_id:
        raise ValueError("cad_analysis_id is required.")

    analysis_path = CAD_WORKSPACE_DIR / f"{analysis_id}.json"
    if not analysis_path.exists():
        raise ValueError("Unknown cad_analysis_id.")
    return json.loads(analysis_path.read_text(encoding="utf-8"))


def _save_apply_snapshot(snapshot: dict) -> None:
    apply_id = str(snapshot.get("apply_id") or "").strip()
    if not apply_id:
        raise ValueError("Bridge apply snapshot requires apply_id.")
    snapshot_path = BRIDGE_APPLY_DIR / f"{apply_id}.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")


def _load_apply_snapshot(apply_id: str) -> dict:
    resolved_apply_id = str(apply_id or "").strip()
    if not resolved_apply_id:
        raise ValueError("apply_id is required.")

    snapshot_path = BRIDGE_APPLY_DIR / f"{resolved_apply_id}.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(resolved_apply_id)
    return json.loads(snapshot_path.read_text(encoding="utf-8"))
