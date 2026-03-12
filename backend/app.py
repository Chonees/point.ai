"""
app.py — Point.ai Backend
FastAPI: prompt/image -> Claude -> JSON -> DXF

Run: uvicorn backend.app:app --reload
"""
import os
import uuid
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional

import anthropic
from dotenv import load_dotenv

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

# Import generator (lives in backend/ alongside app.py)
from generator import generate

app = FastAPI(title="Point.ai", version="0.1.0")

# CORS for dev (Vite runs on :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated DXF files from a temp directory
DXF_DIR = Path(tempfile.gettempdir()) / "pointai_dxf"
DXF_DIR.mkdir(exist_ok=True)


# ─── MODELS ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    image: Optional[str] = None  # base64 encoded image


class GenerateResponse(BaseModel):
    dxf_url: str
    plan: dict


# ─── CLAUDE PROMPT ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a residential floor plan architect for Pointe Homes.
Given a text description (and optionally an image) of a floor plan, produce a JSON object.

RULES:
- All measurements in INCHES (1 foot = 12 inches)
- Wall thickness is 4 inches (handled by the generator, don't include in room dimensions)
- Room coordinates (x, y) are bottom-left corner of the room rectangle
- Rooms should tile together (adjacent rooms share edges)
- Door width: 32-36" standard, 60-72" sliding, 144-192" garage
- Window width: 36-60" typical
- offset = distance along the wall from the room's corner to the opening start

JSON SCHEMA:
{
  "model": "string - name of the floor plan",
  "rooms": [
    {
      "name": "string - room name in CAPS (e.g. LIVING, BED 1, GARAGE)",
      "x": number,
      "y": number,
      "w": number,
      "h": number,
      "doors": [
        {
          "wall": "bottom|top|left|right",
          "offset": number,
          "width": number,
          "type": "normal|garage|sliding" (optional, default normal)
        }
      ],
      "windows": [
        {
          "wall": "bottom|top|left|right",
          "offset": number,
          "width": number
        }
      ]
    }
  ]
}

EXAMPLE:
Prompt: "Simple 2 bedroom house with living room and garage"
{
  "model": "Simple 2BR",
  "rooms": [
    {"name": "GARAGE", "x": 0, "y": 0, "w": 288, "h": 240,
     "doors": [{"wall": "bottom", "offset": 60, "width": 192, "type": "garage"}]},
    {"name": "LIVING", "x": 288, "y": 0, "w": 360, "h": 240,
     "doors": [{"wall": "left", "offset": 100, "width": 36}],
     "windows": [{"wall": "bottom", "offset": 120, "width": 60}]},
    {"name": "BED 1", "x": 288, "y": 240, "w": 180, "h": 168,
     "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
     "windows": [{"wall": "top", "offset": 50, "width": 48}]},
    {"name": "BED 2", "x": 468, "y": 240, "w": 180, "h": 168,
     "doors": [{"wall": "bottom", "offset": 20, "width": 32}],
     "windows": [{"wall": "top", "offset": 50, "width": 48}]}
  ]
}

Return ONLY valid JSON. No markdown, no explanation."""


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Point.ai</h1><p>Run <code>npm run build</code> in frontend/</p>")


# Mount React static assets (JS/CSS bundles)
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest):
    content = []

    if req.image:
        media_type = "image/png"
        image_data = req.image
        if "," in req.image:
            header, image_data = req.image.split(",", 1)
            if "jpeg" in header:
                media_type = "image/jpeg"
            elif "webp" in header:
                media_type = "image/webp"

        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            }
        })

    content.append({"type": "text", "text": req.prompt})

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        plan = json.loads(response_text)

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

    return GenerateResponse(
        dxf_url=f"/downloads/{filename}",
        plan=plan,
    )


@app.get("/downloads/{filename}")
async def download_dxf(filename: str):
    path = DXF_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(path),
        media_type="application/dxf",
        filename=filename,
    )
