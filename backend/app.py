"""
app.py — Point.ai Backend
FastAPI: image -> inference -> structure -> DXF

Run: uvicorn backend.app:app --reload
"""
import uuid
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from dotenv import load_dotenv

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

from .models import (
    GenerateStructureRequest,
    GenerateStructureResponse,
    ParseStructureRequest,
    ParseStructureResponse,
)
from .artifacts import ARTIFACT_DIR, save_structure_artifacts
from .cubicasa_inference import warmup_models
from .observability import log_event
from .worker_client import infer_structure
from .worker_contract import WorkerError
from .plan_parser import parse_structure_payload
from .structural_generator import generate as generate_structural
from .mitunet_inference import (
    MITUNET_BACKEND,
    build_mitunet_region_plan,
    generate_mitunet_region_dxf,
    regions_to_wall_annotations,
)
from .ensemble_inference import ENSEMBLE_BACKEND
from .dxf_preview import build_dxf_preview
from .bom_generator import generate_bom, export_bom_csv

# App
app = FastAPI(title="Point.ai", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# DXF output directory
DXF_DIR = Path(tempfile.gettempdir()) / "pointai_dxf"
DXF_DIR.mkdir(exist_ok=True)


# ─── STARTUP ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _warmup() -> None:
    """Pre-load available CubiCasa models so the first request doesn't cold-start."""
    warmup_models()


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Point.ai</h1><p>Run <code>npm run build</code> in frontend/</p>")


# Mount React static assets
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACT_DIR)), name="artifacts")



@app.post("/api/v2/parse-structure", response_model=ParseStructureResponse)
async def api_parse_structure(req: ParseStructureRequest):
    try:
        parsed, image_b64, debug_overlay_b64 = _parse_v2_input(
            req.plan,
            req.structure,
            req.image,
            req.scale_hint,
            req.model_variant,
        )
    except WorkerError as e:
        log_event("api.parse_structure.worker_error", code=e.code, message=e.message)
        raise HTTPException(status_code=502, detail=f"[{e.code}] {e.message}")
    except ValueError as e:
        log_event("api.parse_structure.validation_error", message=str(e))
        raise HTTPException(status_code=422, detail=str(e))

    request_id = uuid.uuid4().hex[:12]
    infer_result = parsed.get("_infer_result") or {}
    auto_anns = infer_result.get("_auto_annotations", [])
    artifact_urls = save_structure_artifacts(
        request_id=request_id,
        structure=parsed["structure"],
        quality_metrics=parsed["quality_metrics"],
        image_b64=image_b64,
        debug_overlay_b64=debug_overlay_b64,
        auto_annotations=auto_anns or None,
    )
    log_event(
        "api.parse_structure.success",
        request_id=request_id,
        wall_count=len(parsed["structure"].get("walls", [])),
        opening_count=len(parsed["structure"].get("openings", [])),
    )
    return ParseStructureResponse(
        structure=parsed["structure"],
        preview_url=artifact_urls["preview_url"],
        artifact_urls=artifact_urls,
        quality_metrics=parsed["quality_metrics"],
        needs_review=parsed["needs_review"],
        review_flags=parsed["review_flags"],
        auto_annotations=auto_anns or None,
    )


@app.post("/api/v2/generate-dxf", response_model=GenerateStructureResponse)
async def api_generate_v2(req: GenerateStructureRequest):
    try:
        parsed, image_b64, debug_overlay_b64 = _parse_v2_input(
            req.plan,
            req.structure,
            req.image,
            req.scale_hint,
            req.model_variant,
        )
    except WorkerError as e:
        log_event("api.generate_dxf.worker_error", code=e.code, message=e.message)
        raise HTTPException(status_code=502, detail=f"[{e.code}] {e.message}")
    except ValueError as e:
        log_event("api.generate_dxf.validation_error", message=str(e))
        raise HTTPException(status_code=422, detail=str(e))

    request_id = uuid.uuid4().hex[:12]
    filename = f"{request_id}.dxf"
    out_path = str(DXF_DIR / filename)

    # Calibrate scale from user-provided square footage
    if req.scale_sqft and req.scale_sqft > 0:
        _apply_sqft_calibration(parsed["structure"], req.scale_sqft)

    dxf_mode = _resolve_dxf_mode(parsed)
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"].setdefault("structure_meta", {})
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode
    user_has_annotations = req.annotations is not None

    try:
        if dxf_mode == "mask_regions":
            infer_result = parsed.get("_infer_result") or {}
            auto_anns = infer_result.get("_auto_annotations", [])
            if user_has_annotations:
                # User reviewed & edited — use ONLY their annotations.
                # Their set already includes walls + doors + windows they kept.
                merged_anns = req.annotations
            else:
                # First run: auto-detected openings only (walls come from mask).
                merged_anns = auto_anns

            # Build region plan from wall mask
            region_plan = build_mitunet_region_plan(infer_result, annotations=merged_anns)
            parsed["quality_metrics"]["dxf_region_count"] = region_plan["meta"]["region_count"]
            parsed["structure"]["structure_meta"]["dxf_region_plan"] = region_plan
            parsed["structure"]["structure_meta"]["mitunet_region_debug"] = region_plan.get("debug", {})
            parsed["structure"]["structure_meta"]["provenance"] = region_plan["meta"].get("provenance", {})

            if user_has_annotations:
                # User edited: skip mask regions, draw everything from annotations.
                # Wall annotations already include the walls they want.
                generate_mitunet_region_dxf(region_plan, out_path, annotations=merged_anns, skip_regions=True)
            else:
                # First run: draw walls from mask + doors/windows from annotations.
                generate_mitunet_region_dxf(region_plan, out_path, annotations=merged_anns)
        else:
            generate_structural(parsed["structure"], out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DXF generation failed: {e}")

    infer_result_for_anns = parsed.get("_infer_result") or {}
    auto_anns_response = infer_result_for_anns.get("_auto_annotations", [])
    # Include wall regions as editable annotations on first run
    region_plan_data = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
    if region_plan_data and not user_has_annotations:
        wall_anns = regions_to_wall_annotations(region_plan_data)
        auto_anns_response = wall_anns + auto_anns_response

    # Build preview from the ACTUAL DXF output (not just postprocessed inference)
    dxf_preview_img = None
    try:
        region_plan_for_preview = parsed["structure"].get("structure_meta", {}).get("dxf_region_plan")
        dxf_preview_img = build_dxf_preview(
            out_path,
            image_b64=image_b64,
            region_plan=region_plan_for_preview,
        )
    except Exception as exc:
        log_event("api.generate_dxf.dxf_preview_error", error=str(exc))

    artifact_urls = save_structure_artifacts(
        request_id=request_id,
        structure=parsed["structure"],
        quality_metrics=parsed["quality_metrics"],
        image_b64=image_b64,
        debug_overlay_b64=debug_overlay_b64,
        auto_annotations=auto_anns_response or None,
        dxf_preview=dxf_preview_img,
    )
    log_event(
        "api.generate_dxf.success",
        request_id=request_id,
        wall_count=len(parsed["structure"].get("walls", [])),
        opening_count=len(parsed["structure"].get("openings", [])),
    )
    bom = generate_bom(parsed["structure"])
    return GenerateStructureResponse(
        dxf_url=f"/downloads/{filename}",
        preview_url=artifact_urls["preview_url"],
        artifact_urls=artifact_urls,
        structure=parsed["structure"],
        needs_review=parsed["needs_review"],
        scale_status=parsed["structure"]["structure_meta"]["scale_status"],
        quality_metrics=parsed["quality_metrics"],
        review_flags=parsed["review_flags"],
        auto_annotations=auto_anns_response or None,
        bom=bom,
    )


@app.post("/api/v2/bom-csv")
async def api_bom_csv(req: dict):
    """Generate BOM CSV from structure."""
    from fastapi.responses import Response
    bom = generate_bom(req.get("structure", {}))
    csv_content = export_bom_csv(bom)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bom.csv"},
    )


@app.get("/downloads/{filename}")
async def download_dxf(filename: str):
    path = DXF_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="application/dxf", filename=filename)




def _parse_v2_input(
    plan: dict | None,
    structure: dict | None,
    image: str | None,
    scale_hint: float | None,
    model_variant: str | None,
) -> tuple[dict, str | None, str | None]:
    if structure is not None:
        parsed = parse_structure_payload(structure=structure, scale_hint=scale_hint)
        return parsed, None, structure.get("inference_debug", {}).get("debug_overlay_b64")

    if plan is not None:
        parsed = parse_structure_payload(plan=plan, scale_hint=scale_hint)
        return parsed, None, None

    if image is not None:
        if model_variant == "r2v":
            inferred = infer_structure(image, backend="r2v_local")
        elif model_variant == "mitunet":
            inferred = infer_structure(image, backend="mitunet_local")
        elif model_variant == "ensemble":
            inferred = infer_structure(image, backend="ensemble_local")
        else:
            options = {"model_variant": model_variant} if model_variant else None
            if options is None:
                inferred = infer_structure(image)
            else:
                inferred = infer_structure(image, options=options)
        parsed = parse_structure_payload(structure=inferred, scale_hint=scale_hint)
        parsed["quality_metrics"]["inference_backend"] = (
            inferred.get("inference_debug", {}).get("backend") or inferred.get("source")
        )
        parsed["quality_metrics"]["model_variant"] = (
            inferred.get("inference_debug", {}).get("model_variant") or model_variant or "baseline"
        )
        # Preserve raw infer result for diagnostics and benchmark tooling.
        parsed["_infer_result"] = inferred
        return parsed, image, inferred.get("inference_debug", {}).get("debug_overlay_b64")

    raise ValueError("One of structure, plan or image must be provided.")


def _resolve_dxf_mode(parsed: dict) -> str:
    infer_result = parsed.get("_infer_result") or {}
    source = infer_result.get("source", "")
    supports_mask_regions = (
        source in (MITUNET_BACKEND, ENSEMBLE_BACKEND)
        and "_wall_mask" in infer_result
    )
    return "mask_regions" if supports_mask_regions else "structural"


def _apply_sqft_calibration(structure: dict, target_sqft: float) -> None:
    """Compute scale_hint from user-provided total floor area (sqft).

    Uses the bounding box of all walls in pixel space to derive a
    pixels-to-inches conversion factor.
    """
    import math

    walls = structure.get("walls") or []
    if not walls:
        return

    xs, ys = [], []
    for wall in walls:
        for pt in wall.get("polyline", []):
            xs.append(float(pt["x"]))
            ys.append(float(pt["y"]))
    if not xs:
        return

    bbox_w_px = max(xs) - min(xs)
    bbox_h_px = max(ys) - min(ys)
    bbox_area_px = bbox_w_px * bbox_h_px
    if bbox_area_px < 1:
        return

    # target_sqft → sq inches → scale factor
    target_sqin = target_sqft * 144.0
    scale = math.sqrt(target_sqin / bbox_area_px)

    meta = structure.setdefault("structure_meta", {})
    meta["scale_hint"] = round(scale, 6)
    meta["scale_status"] = "calibrated"
    meta["unit"] = "inch"
    meta["calibration_source"] = "user_sqft"
    meta["calibration_sqft"] = target_sqft
