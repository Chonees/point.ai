"""
app.py — Point.ai Backend
FastAPI: prompt/image -> Claude -> JSON -> DXF

Run: uvicorn backend.app:app --reload
"""
import uuid
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel as _PydanticBaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from dotenv import load_dotenv

import anthropic

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

# Import backend modules
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generator import generate

from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateStructureRequest,
    GenerateStructureResponse,
    ParseStructureRequest,
    ParseStructureResponse,
)
from .claude import analyze_image, generate_plan
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
)
from .validation import validate_plan

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


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def api_analyze(req: AnalyzeRequest):
    try:
        description = analyze_image(req.image)
        return AnalyzeResponse(description=description)
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")


@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest):
    try:
        plan = generate_plan(req.prompt, req.image)
        plan = validate_plan(plan)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Claude returned invalid JSON: {e}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    filename = f"{uuid.uuid4().hex[:12]}.dxf"
    out_path = str(DXF_DIR / filename)

    try:
        parsed = parse_structure_payload(plan=plan)
        generate_structural(parsed["structure"], out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DXF generation failed: {e}")

    return GenerateResponse(dxf_url=f"/downloads/{filename}", plan=plan)


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
    artifact_urls = save_structure_artifacts(
        request_id=request_id,
        structure=parsed["structure"],
        quality_metrics=parsed["quality_metrics"],
        image_b64=image_b64,
        debug_overlay_b64=debug_overlay_b64,
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

    dxf_mode = _resolve_dxf_mode(parsed)
    parsed["quality_metrics"]["dxf_mode"] = dxf_mode
    parsed["structure"].setdefault("structure_meta", {})
    parsed["structure"]["structure_meta"]["dxf_mode"] = dxf_mode

    try:
        if dxf_mode == "mask_regions":
            infer_result = parsed.get("_infer_result") or {}
            region_plan = build_mitunet_region_plan(infer_result, annotations=req.annotations)
            parsed["quality_metrics"]["dxf_region_count"] = region_plan["meta"]["region_count"]
            parsed["structure"]["structure_meta"]["dxf_region_plan"] = region_plan
            parsed["structure"]["structure_meta"]["mitunet_region_debug"] = region_plan.get("debug", {})
            parsed["structure"]["structure_meta"]["provenance"] = region_plan["meta"].get("provenance", {})
            generate_mitunet_region_dxf(region_plan, out_path, annotations=req.annotations)
        else:
            generate_structural(parsed["structure"], out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DXF generation failed: {e}")

    artifact_urls = save_structure_artifacts(
        request_id=request_id,
        structure=parsed["structure"],
        quality_metrics=parsed["quality_metrics"],
        image_b64=image_b64,
        debug_overlay_b64=debug_overlay_b64,
    )
    log_event(
        "api.generate_dxf.success",
        request_id=request_id,
        wall_count=len(parsed["structure"].get("walls", [])),
        opening_count=len(parsed["structure"].get("openings", [])),
    )
    return GenerateStructureResponse(
        dxf_url=f"/downloads/{filename}",
        preview_url=artifact_urls["preview_url"],
        artifact_urls=artifact_urls,
        structure=parsed["structure"],
        needs_review=parsed["needs_review"],
        scale_status=parsed["structure"]["structure_meta"]["scale_status"],
        quality_metrics=parsed["quality_metrics"],
        review_flags=parsed["review_flags"],
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
    supports_mask_regions = (
        infer_result.get("source") == MITUNET_BACKEND and "_wall_mask" in infer_result
    )
    return "mask_regions" if supports_mask_regions else "structural"
