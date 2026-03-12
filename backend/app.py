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

from .models import AnalyzeRequest, AnalyzeResponse, GenerateRequest, GenerateResponse
from .claude import analyze_image, generate_plan
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
        generate(plan, out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DXF generation failed: {e}")

    return GenerateResponse(dxf_url=f"/downloads/{filename}", plan=plan)


@app.get("/downloads/{filename}")
async def download_dxf(filename: str):
    path = DXF_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="application/dxf", filename=filename)
