"""
app.py — Point.ai Backend
FastAPI: image -> inference -> structure -> DXF

Run: uvicorn backend.app:app --reload
"""
import os
import uuid
import tempfile
from contextlib import asynccontextmanager
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
from .worker_contract import WorkerError
from .services.parse_service import parse_v2_input, resolve_dxf_mode
from .services.generate_dxf_service import generate_dxf


# ─── LIFESPAN ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup_models()
    yield


# ─── APP ─────────────────────────────────────────────────────────────────────

_cors_origins = os.getenv(
    "POINTAI_CORS_ORIGINS", "http://localhost:5173"
).split(",")

app = FastAPI(title="Point.ai", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

DXF_DIR = Path(tempfile.gettempdir()) / "pointai_dxf"
DXF_DIR.mkdir(exist_ok=True)


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Point.ai</h1><p>Run <code>npm run build</code> in frontend/</p>")


if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACT_DIR)), name="artifacts")


@app.post("/api/v2/parse-structure", response_model=ParseStructureResponse)
async def api_parse_structure(req: ParseStructureRequest):
    try:
        parsed, image_b64, debug_overlay_b64 = parse_v2_input(
            req.plan, req.structure, req.image, req.scale_hint, req.model_variant,
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
        parsed, image_b64, debug_overlay_b64 = parse_v2_input(
            req.plan, req.structure, req.image, req.scale_hint, req.model_variant,
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
    dxf_mode = resolve_dxf_mode(parsed)

    try:
        dxf_result = generate_dxf(
            parsed=parsed,
            out_path=out_path,
            dxf_mode=dxf_mode,
            annotations=req.annotations,
            total_area=req.total_area if req.total_area is not None else req.total_sqft,
            image_b64=image_b64,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DXF generation failed: {e}")

    artifact_urls = save_structure_artifacts(
        request_id=request_id,
        structure=parsed["structure"],
        quality_metrics=parsed["quality_metrics"],
        image_b64=image_b64,
        debug_overlay_b64=debug_overlay_b64,
        auto_annotations=dxf_result["auto_annotations"],
        dxf_preview=dxf_result["dxf_preview"],
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
        auto_annotations=dxf_result["auto_annotations"],
        computed_rooms=dxf_result["computed_rooms"],
        region_overlay=dxf_result["region_overlay"],
    )


@app.get("/downloads/{filename}")
async def download_dxf(filename: str):
    path = DXF_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="application/dxf", filename=filename)
