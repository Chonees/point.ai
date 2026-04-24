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
        site_plan = cad_analysis.get("site_plan") or {}
        site_bbox = site_plan.get("bbox") if isinstance(site_plan, dict) else None
        if isinstance(site_bbox, dict) and site_bbox.get("width") and site_bbox.get("height"):
            buildable_bbox = {
                "x1": float(site_bbox.get("x1", 0.0)),
                "y1": float(site_bbox.get("y1", 0.0)),
                "x2": float(site_bbox.get("x2", 0.0)),
                "y2": float(site_bbox.get("y2", 0.0)),
                "width": float(site_bbox.get("width", 0.0)),
                "height": float(site_bbox.get("height", 0.0)),
            }
            fit_warnings = [
                "No se detectó un buildable_polygon/capa explícita; se usó la bbox del site plan como envelope provisional."
            ]
        else:
            raise ValueError("Bridge MVP v1 needs an extracted buildable bbox.")
    else:
        fit_warnings = []

    plan_bbox = plan_payload.get("footprint_bbox") or {}
    warnings = [
        "Bridge MVP v1 anchors SEMINOLE2000 at the buildable bbox origin for a fixed 1:1 registration lane.",
    ]
    if fit.get("buildable_polygon"):
        warnings.append("Buildable polygon detected and used for polygonal fit check.")
    if fit_warnings:
        warnings.extend(fit_warnings)
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
    }, warnings


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
        "applied_review": _build_applied_review(
            apply_id=apply_id,
            plan_name=plan_payload["name"],
            cad_analysis=cad_analysis,
            applied=applied,
        ),
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


def _build_applied_review(*, apply_id: str, plan_name: str, cad_analysis: dict, applied: dict) -> dict:
    plan_payload = (applied.get("applied_plan") or {}).get("plan") or {}
    registration = applied.get("registration_summary") or {}
    transform = registration.get("transform") or {}
    canonical_unit = (
        registration.get("canonical_unit")
        or cad_analysis.get("canonical_unit")
        or "inch"
    )
    fit_summary = cad_analysis.get("fit_summary") or {}
    footprint_bbox = plan_payload.get("footprint_bbox")
    registered_footprint_bbox = (
        registration.get("registered_plan_bbox")
        or _transform_bbox(footprint_bbox, transform=transform)
    )
    floor_entities = _build_plan_entities(plan_payload)
    floor_rooms = _build_plan_rooms(plan_payload)
    site_plan = cad_analysis.get("site_plan") or _empty_view(role="site_plan")
    site_bbox = (site_plan.get("bbox") or {}) if isinstance(site_plan, dict) else {}

    return {
        "analysis_id": apply_id,
        "source_name": f"{plan_name} applied",
        "source_format": "site_fit_apply",
        "canonical_unit": canonical_unit,
        "conversion_status": "site_fit_apply",
        "conversion_note": "Applied site-fit preview built from applied plan plus registration.",
        "floor_plan": {
            "role": "floor_plan",
            "bbox": footprint_bbox,
            "summary": _build_view_summary(floor_entities),
            "entities": floor_entities,
            "rooms": floor_rooms,
            "measurements": _bbox_measurements(footprint_bbox, source="applied_plan_bbox"),
        },
        "site_plan": site_plan,
        "side_by_side": {
            "canonical_unit": canonical_unit,
            "gap": 0.0,
            "floor_width": float((footprint_bbox or {}).get("width") or 0.0),
            "site_width": float(site_bbox.get("width") or 0.0),
            "max_height": max(
                float((footprint_bbox or {}).get("height") or 0.0),
                float(site_bbox.get("height") or 0.0),
            ),
        },
        "fit_summary": {
            "comparison_unit": canonical_unit,
            "basis": fit_summary.get("basis") or "buildable_polygon",
            "footprint_bbox": footprint_bbox,
            "registered_footprint_bbox": registered_footprint_bbox,
            "property_bbox": fit_summary.get("property_bbox"),
            "buildable_bbox": fit_summary.get("buildable_bbox"),
            "buildable_polygon": fit_summary.get("buildable_polygon"),
            "width_delta": fit_summary.get("width_delta"),
            "height_delta": fit_summary.get("height_delta"),
            "fits_within_buildable_bbox": _coalesce_fit_flag(
                fit_summary.get("fits_within_buildable_bbox"),
                applied=applied,
            ),
            "fits_within_buildable_polygon": _coalesce_fit_flag(
                fit_summary.get("fits_within_buildable_polygon"),
                applied=applied,
            ),
        },
        "warnings": list(applied.get("warnings") or []),
    }


def _coalesce_fit_flag(flag: bool | None, *, applied: dict) -> bool | None:
    if flag is not None:
        return flag
    compliance = (applied.get("compliance_summary") or {}).get("status")
    if compliance == "pass":
        return True
    return None


def _empty_view(*, role: str) -> dict:
    return {
        "role": role,
        "bbox": None,
        "summary": {
            "entity_count": 0,
            "line_count": 0,
            "polyline_count": 0,
            "text_count": 0,
        },
        "entities": [],
        "rooms": [],
        "measurements": None,
    }


def _build_view_summary(entities: list[dict]) -> dict:
    line_count = sum(1 for entity in entities if str(entity.get("type") or "").lower() == "line")
    polyline_count = sum(1 for entity in entities if str(entity.get("type") or "").lower() == "polyline")
    return {
        "entity_count": len(entities),
        "line_count": line_count,
        "polyline_count": polyline_count,
        "text_count": 0,
    }


def _build_plan_entities(plan_payload: dict) -> list[dict]:
    entities: list[dict] = []
    for wall in plan_payload.get("walls") or []:
        start = wall.get("start")
        end = wall.get("end")
        if not isinstance(start, dict) or not isinstance(end, dict):
            continue
        entities.append({
            "type": "line",
            "layer": "BRIDGE_APPLY_PLAN",
            "start": _copy_point(start),
            "end": _copy_point(end),
            "points": [],
            "bbox": _bbox_from_points([start, end]),
        })

    for opening in plan_payload.get("openings") or []:
        start = opening.get("start")
        end = opening.get("end")
        if not isinstance(start, dict) or not isinstance(end, dict):
            continue
        entities.append({
            "type": "line",
            "layer": "BRIDGE_APPLY_OPENINGS",
            "start": _copy_point(start),
            "end": _copy_point(end),
            "points": [],
            "bbox": _bbox_from_points([start, end]),
        })
    return entities


def _build_plan_rooms(plan_payload: dict) -> list[dict]:
    rooms: list[dict] = []
    for room in plan_payload.get("rooms") or []:
        bbox = room.get("bbox")
        centroid = room.get("centroid")
        polygon = room.get("polygon") or []
        if not isinstance(bbox, dict) or not isinstance(centroid, dict) or len(polygon) < 3:
            continue
        rooms.append({
            "name": room.get("name") or room.get("room_id") or "ROOM",
            "polygon": [_copy_point(point) for point in polygon if isinstance(point, dict)],
            "bbox": _copy_bbox(bbox),
            "centroid": _copy_point(centroid),
            "width": float(room.get("width") or bbox.get("width") or 0.0),
            "height": float(room.get("height") or bbox.get("height") or 0.0),
            "area": float(room.get("area") or 0.0),
            "measurement_source": room.get("measurement_source") or "site_fit_applied",
        })
    return rooms


def _transform_bbox(bbox: dict | None, *, transform: dict) -> dict | None:
    if not isinstance(bbox, dict):
        return None
    corners = [
        {"x": bbox["x1"], "y": bbox["y1"]},
        {"x": bbox["x2"], "y": bbox["y1"]},
        {"x": bbox["x2"], "y": bbox["y2"]},
        {"x": bbox["x1"], "y": bbox["y2"]},
    ]
    transformed = [_transform_point(point, transform=transform) for point in corners]
    return _bbox_from_points(transformed)


def _transform_point(point: dict | None, *, transform: dict) -> dict | None:
    if not isinstance(point, dict):
        return None
    scale = float(transform.get("scale") or 1.0)
    translate_x = float(transform.get("translate_x") or 0.0)
    translate_y = float(transform.get("translate_y") or 0.0)
    rotation = float(transform.get("rotation_degrees") or 0.0)
    if rotation not in {0.0, 0, -0.0}:
        raise ValueError("Bridge apply preview currently supports 0-degree registration only.")
    return {
        "x": float(point.get("x") or 0.0) * scale + translate_x,
        "y": float(point.get("y") or 0.0) * scale + translate_y,
    }


def _copy_point(point: dict) -> dict:
    return {
        "x": float(point.get("x") or 0.0),
        "y": float(point.get("y") or 0.0),
    }


def _copy_bbox(bbox: dict) -> dict:
    return {
        "x1": float(bbox.get("x1") or 0.0),
        "y1": float(bbox.get("y1") or 0.0),
        "x2": float(bbox.get("x2") or 0.0),
        "y2": float(bbox.get("y2") or 0.0),
        "width": float(bbox.get("width") or 0.0),
        "height": float(bbox.get("height") or 0.0),
    }


def _bbox_from_points(points: list[dict | None]) -> dict | None:
    numeric_points = [point for point in points if isinstance(point, dict)]
    if not numeric_points:
        return None
    xs = [float(point.get("x") or 0.0) for point in numeric_points]
    ys = [float(point.get("y") or 0.0) for point in numeric_points]
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _bbox_measurements(bbox: dict | None, *, source: str) -> dict | None:
    if not isinstance(bbox, dict):
        return None
    return {
        "width": float(bbox.get("width") or 0.0),
        "height": float(bbox.get("height") or 0.0),
        "source": source,
    }
