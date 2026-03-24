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
from .mitunet_inference import generate_mitunet_dxf, MITUNET_BACKEND
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

    try:
        # Use MitUNet's own DXF generator (template + rect hatch) when available
        infer_result = parsed.get("_infer_result") or {}
        if infer_result.get("source") == MITUNET_BACKEND and "_wall_mask" in infer_result:
            generate_mitunet_dxf(infer_result, out_path)
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


# ---------------------------------------------------------------------------
# Add Doors & Windows via CubiCasa + AutoCAD MCP
# ---------------------------------------------------------------------------

class AddOpeningsRequest(_PydanticBaseModel):
    image: str
    kind: str = "all"  # "doors", "windows", or "all"


class AddOpeningsResponse(_PydanticBaseModel):
    status: str
    count: int
    message: str | None = None


# Pointe Homes standards
_DOOR_SLAB_THICKNESS = 1.5  # inches
_DOOR_LAYER = "DOORS"
_DOOR_COLOR = 157
_WIN_LAYER = "WINS"
_WIN_COLOR = 121
_SILL_OFFSET = 5  # inches


def _cubicasa_to_dxf_coords(px: float, py: float, scale: float,
                             offset_x: float, offset_y: float) -> tuple[float, float]:
    return px * scale + offset_x, py * scale + offset_y


def _generate_door_lisp(dx: float, dy: float, dspan: float, orientation: str) -> list[str]:
    """Generate Pointe Homes door LISP: 2 parallel lines (slab) + 90° arc swing."""
    DS = _DOOR_SLAB_THICKNESS
    lines = []
    if orientation == "horizontal":
        # Slab: two parallel vertical lines
        lines.append(f'(command "LINE" "{dx:.2f},{dy:.2f}" "{dx:.2f},{dy + dspan:.2f}" "")')
        lines.append(f'(command "LINE" "{dx + DS:.2f},{dy:.2f}" "{dx + DS:.2f},{dy + dspan:.2f}" "")')
        # Arc swing 90°
        lines.append(f'(command "ARC" "C" "{dx:.2f},{dy:.2f}" "{dx + dspan:.2f},{dy:.2f}" "A" "90")')
    else:
        # Slab: two parallel horizontal lines
        lines.append(f'(command "LINE" "{dx:.2f},{dy:.2f}" "{dx + dspan:.2f},{dy:.2f}" "")')
        lines.append(f'(command "LINE" "{dx:.2f},{dy + DS:.2f}" "{dx + dspan:.2f},{dy + DS:.2f}" "")')
        # Arc swing 90°
        lines.append(f'(command "ARC" "C" "{dx:.2f},{dy:.2f}" "{dx:.2f},{dy + dspan:.2f}" "A" "90")')
    return lines


def _generate_window_lisp(dx: float, dy: float, dspan: float, orientation: str) -> list[str]:
    """Generate Pointe Homes window LISP: 3 parallel lines + 2 end caps + sill."""
    lines = []
    if orientation == "horizontal":
        x1 = dx - dspan / 2
        x2 = dx + dspan / 2
        # 3 parallel lines
        lines.append(f'(command "LINE" "{x1:.2f},{dy:.2f}" "{x2:.2f},{dy:.2f}" "")')
        lines.append(f'(command "LINE" "{x1:.2f},{dy - 1:.2f}" "{x2:.2f},{dy - 1:.2f}" "")')
        lines.append(f'(command "LINE" "{x1:.2f},{dy - 2:.2f}" "{x2:.2f},{dy - 2:.2f}" "")')
        # End caps
        lines.append(f'(command "LINE" "{x1:.2f},{dy - 1:.2f}" "{x1:.2f},{dy - 2:.2f}" "")')
        lines.append(f'(command "LINE" "{x2:.2f},{dy - 1:.2f}" "{x2:.2f},{dy - 2:.2f}" "")')
        # Sill exterior
        lines.append(f'(command "LINE" "{x1:.2f},{dy - {_SILL_OFFSET}:.2f}" "{x2:.2f},{dy - {_SILL_OFFSET}:.2f}" "")')
    else:
        y1 = dy - dspan / 2
        y2 = dy + dspan / 2
        # 3 parallel lines
        lines.append(f'(command "LINE" "{dx:.2f},{y1:.2f}" "{dx:.2f},{y2:.2f}" "")')
        lines.append(f'(command "LINE" "{dx - 1:.2f},{y1:.2f}" "{dx - 1:.2f},{y2:.2f}" "")')
        lines.append(f'(command "LINE" "{dx + 1:.2f},{y1:.2f}" "{dx + 1:.2f},{y2:.2f}" "")')
        # End caps
        lines.append(f'(command "LINE" "{dx - 1:.2f},{y1:.2f}" "{dx:.2f},{y1:.2f}" "")')
        lines.append(f'(command "LINE" "{dx - 1:.2f},{y2:.2f}" "{dx:.2f},{y2:.2f}" "")')
        # Sill exterior
        lines.append(f'(command "LINE" "{dx + {_SILL_OFFSET}:.2f},{y1:.2f}" "{dx + {_SILL_OFFSET}:.2f},{y2:.2f}" "")')
    return lines


@app.post("/api/v2/add-openings", response_model=AddOpeningsResponse)
async def api_add_openings(req: AddOpeningsRequest):
    """Detect doors/windows with CubiCasa and send LISP to AutoCAD."""
    from .cubicasa_inference import infer_cubicasa
    from .mitunet_inference import _PLAN_X1, _PLAN_Y1, _PLAN_X2, _PLAN_Y2
    from pathlib import Path

    try:
        result = infer_cubicasa(req.image, model_variant="baseline")
        all_openings = result.get("openings", [])
        img_size = result.get("structure_meta", {}).get("image_size", {})
        img_w = img_size.get("width", 800)
        img_h = img_size.get("height", 600)

        # Filter by kind
        if req.kind == "doors":
            openings = [o for o in all_openings if o.get("kind") == "door"]
        elif req.kind == "windows":
            openings = [o for o in all_openings if o.get("kind") == "window"]
        else:
            openings = all_openings

        if not openings:
            return AddOpeningsResponse(status="no_openings", count=0,
                                       message="No openings detected.")

        # Scale to DXF template
        plan_w = _PLAN_X2 - _PLAN_X1
        plan_h = _PLAN_Y2 - _PLAN_Y1
        if (img_w / img_h) > (plan_w / plan_h):
            scale = plan_w / img_w
            offset_x = _PLAN_X1
            offset_y = _PLAN_Y1 + (plan_h - img_h * scale) / 2
        else:
            scale = plan_h / img_h
            offset_x = _PLAN_X1 + (plan_w - img_w * scale) / 2
            offset_y = _PLAN_Y1

        lisp_lines = []

        # Setup layers with Pointe Homes colors
        if req.kind in ("doors", "all"):
            lisp_lines.append(f'(command "-LAYER" "M" "{_DOOR_LAYER}" "C" "{_DOOR_COLOR}" "" "")')
        if req.kind in ("windows", "all"):
            lisp_lines.append(f'(command "-LAYER" "M" "{_WIN_LAYER}" "C" "{_WIN_COLOR}" "" "")')

        for opening in openings:
            pos = opening.get("position", {})
            dx, dy = _cubicasa_to_dxf_coords(pos.get("x", 0), pos.get("y", 0),
                                              scale, offset_x, offset_y)
            dspan = opening.get("span", 20) * scale
            orientation = opening.get("orientation", "horizontal")
            kind = opening.get("kind", "door")

            if kind == "door":
                lisp_lines.append(f'(command "-LAYER" "S" "{_DOOR_LAYER}" "")')
                lisp_lines.extend(_generate_door_lisp(dx, dy, dspan, orientation))
            else:
                lisp_lines.append(f'(command "-LAYER" "S" "{_WIN_LAYER}" "")')
                lisp_lines.extend(_generate_window_lisp(dx, dy, dspan, orientation))

        # Write and send
        lisp_dir = Path("C:/temp")
        lisp_dir.mkdir(exist_ok=True)
        lisp_path = lisp_dir / f"pointai_{req.kind}.lsp"
        lisp_path.write_text("\n".join(lisp_lines), encoding="utf-8")

        autocad_status = _send_lisp_to_autocad(str(lisp_path))
        log_event(f"api.add_{req.kind}.success", count=len(openings))

        return AddOpeningsResponse(
            status="ok", count=len(openings),
            message=f"{len(openings)} {req.kind}. {autocad_status}",
        )

    except Exception as e:
        log_event("api.add_openings.error", message=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def _send_lisp_to_autocad(lisp_path: str) -> str:
    """Send a (load ...) command to AutoCAD via PostMessage — no MCP server needed."""
    import sys
    if sys.platform != "win32":
        return "Not on Windows — LISP saved for manual loading"

    try:
        import ctypes
        import win32gui

        # Find AutoCAD window
        windows: list[int] = []

        def callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd).lower()
                if "autocad" in text and ("drawing" in text or ".dwg" in text or ".dxf" in text):
                    result.append(hwnd)
            return True

        win32gui.EnumWindows(callback, windows)

        if not windows:
            return "AutoCAD not found — LISP saved for manual loading"

        hwnd = windows[0]

        # Find MDIClient child for command routing
        mdi_client: list[int] = []

        def find_mdi(child_hwnd, _):
            if win32gui.GetClassName(child_hwnd) == "MDIClient":
                mdi_client.append(child_hwnd)
                return False
            return True

        try:
            win32gui.EnumChildWindows(hwnd, find_mdi, None)
        except Exception:
            pass

        target = mdi_client[0] if mdi_client else hwnd

        WM_CHAR = 0x0102
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_ESCAPE = 0x1B
        post = ctypes.windll.user32.PostMessageW

        # Cancel any pending command
        import time
        for _ in range(2):
            post(target, WM_KEYDOWN, VK_ESCAPE, 0)
            post(target, WM_KEYUP, VK_ESCAPE, 0)
        time.sleep(0.05)

        # Type: (load "C:/temp/pointai_openings.lsp")
        load_cmd = f'(load "{lisp_path.replace(chr(92), "/")}")'
        for ch in load_cmd:
            post(target, WM_CHAR, ord(ch), 0)
        # Enter
        post(target, WM_CHAR, 0x0D, 0)

        return "Sent to AutoCAD"

    except ImportError:
        return "pywin32 not installed — LISP saved for manual loading"
    except Exception as e:
        return f"AutoCAD send failed: {e} — LISP saved for manual loading"


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
        # Preserve raw infer result for MitUNet DXF generator
        parsed["_infer_result"] = inferred
        return parsed, image, inferred.get("inference_debug", {}).get("debug_overlay_b64")

    raise ValueError("One of structure, plan or image must be provided.")
