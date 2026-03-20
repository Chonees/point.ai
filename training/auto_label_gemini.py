"""
auto_label_gemini.py  —  auto-labels floor plan images using Gemini Vision.

Sends each original.jpg to Gemini with a strict color prompt.
Gemini paints the floor plan and returns the colored image.
Saves result as TRAIN ONE.png in the same folder.

Usage:
    set GOOGLE_API_KEY=your_key_here
    python training/auto_label_gemini.py --dataset D:/PointAIData/dataset
    python training/auto_label_gemini.py --dataset D:/PointAIData/dataset --start 12 --end 100
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import io
import base64
import google.genai as genai
from google.genai import types
from PIL import Image

# ---------------------------------------------------------------------------
# Prompt — full context sent on every single call (no memory between calls)
# ---------------------------------------------------------------------------
PROMPT = """Repaint this floor plan image using ONLY these EXACT RGB colors.
Maintain exact geometry. Do NOT add anything new. Paint ONLY what already exists.

EXACT colors — no variations, no gradients, hard pixel edges:
- Walls (thick boundary lines): RGB(32, 37, 45) — very dark navy, almost black. NEVER orange or brown.
- Windows (small rectangles in walls): RGB(69, 142, 255) — bright blue
- Doors (arc/swing lines): RGB(214, 116, 47) — orange
- Bedroom / Master Bedroom / Closet / WIC: RGB(233, 242, 255) — very light blue
- Living / Great Room / Family Room / Den: RGB(250, 241, 221) — light yellow
- Kitchen / Dining / Butler / Pantry: RGB(241, 231, 214) — light peach
- Bathroom / Powder / Laundry / Utility / Mud: RGB(226, 241, 245) — light cyan
- Garage / Storage: RGB(231, 233, 236) — light gray
- Porch / Patio / Outdoor / Entry / Foyer: RGB(244, 249, 239) — very light green
- Furniture, text, dimensions, all other elements: RGB(255, 255, 255) — pure white

Rules:
1. Every pixel = exactly one color from the list above
2. Walls = RGB(32,37,45) dark navy — never orange, never brown
3. Furniture inside rooms = same color as the room floor
4. Return the complete repainted image at the same resolution
"""

MODEL = "gemini-3.1-flash-image-preview"


# ---------------------------------------------------------------------------
# Gemini setup
# ---------------------------------------------------------------------------
def _get_client() -> genai.Client:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY environment variable first")
    return genai.Client(api_key=api_key)


def label_one(client: genai.Client, image_path: Path, out_path: Path, retries: int = 3) -> bool:
    """Send one image to Gemini, save colored result. Returns True on success."""
    for attempt in range(1, retries + 1):
        try:
            img = Image.open(image_path).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            buf.seek(0)

            img_bytes_data = buf.read()
            def _call():
                return client.models.generate_content(
                    model=MODEL,
                    contents=[
                        types.Part.from_bytes(data=img_bytes_data, mime_type="image/jpeg"),
                        types.Part.from_text(text=PROMPT),
                    ],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        temperature=0.0,
                    ),
                )
            ex = ThreadPoolExecutor(max_workers=1)
            future = ex.submit(_call)
            try:
                response = future.result(timeout=120)
            except FuturesTimeout:
                future.cancel()
                ex.shutdown(wait=False, cancel_futures=True)
                raise
            finally:
                ex.shutdown(wait=False, cancel_futures=True)

            for part in response.candidates[0].content.parts:
                if part.inline_data and "image" in part.inline_data.mime_type:
                    img_bytes = part.inline_data.data
                    result = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    result.save(str(out_path))
                    return True

            print(f"    [no image returned] {image_path.parent.name}")
            return False

        except FuturesTimeout:
            err = "TIMEOUT (90s sin respuesta)"
            if attempt < retries:
                print(f"    [RETRY {attempt}/{retries} - esperando 60s] {image_path.parent.name} -> {err}")
                time.sleep(60)
            else:
                print(f"    [FALLO DEFINITIVO - saltando] {image_path.parent.name} -> {err}")
                return False
        except Exception as e:
            err = str(e)
            if attempt < retries:
                print(f"    [RETRY {attempt}/{retries} - esperando 60s] {image_path.parent.name} -> {err[:80]}")
                time.sleep(60)
            else:
                print(f"    [FALLO DEFINITIVO - saltando] {image_path.parent.name} -> {err[:120]}")
                return False
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="D:/PointAIData/dataset")
    parser.add_argument("--start",   type=int, default=1,
                        help="Start from folder number (default: 1)")
    parser.add_argument("--end",     type=int, default=5000,
                        help="End at folder number (default: 5000)")
    parser.add_argument("--delay",   type=float, default=2.0,
                        help="Seconds between API calls (default: 2)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-label folders that already have TRAIN ONE.png")
    args = parser.parse_args()

    client  = _get_client()
    base    = Path(args.dataset)
    folders = sorted(
        f for f in base.iterdir()
        if f.is_dir() and args.start <= int(f.name) <= args.end
    )

    COST_PER_IMAGE = 0.045
    done = skipped = errors = 0
    total_cost = 0.0

    for folder in folders:
        original = folder / "original.jpg"
        if not original.exists():
            original = next(folder.glob("original.*"), None)
        if original is None:
            skipped += 1
            continue

        out = folder / "TRAIN ONE.png"
        if out.exists() and not args.overwrite:
            skipped += 1
            continue

        print(f"  {folder.name} ...", end=" ", flush=True)
        ok = label_one(client, original, out)
        if ok:
            done += 1
            total_cost += COST_PER_IMAGE
            print(f"OK  |  ${COST_PER_IMAGE:.3f}  |  total: ${total_cost:.3f}  |  done: {done}")
        else:
            errors += 1
            print(f"FAIL  |  done: {done}  errors: {errors}  total: ${total_cost:.3f}")

        time.sleep(args.delay)

    print(f"\nDone: {done}  Skipped: {skipped}  Errors: {errors}")


if __name__ == "__main__":
    main()
