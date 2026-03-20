"""
png_to_autocad.py — PNG floor plan → AutoCAD via Claude Vision + MCP

Flow:
  1. Read PNG → base64
  2. Claude Vision extracts rooms/walls/openings as JSON (single call)
  3. lisp_writer converts JSON → LISP → C:/temp/plan.lsp
  4. Print the MCP command to load it (or auto-call if run via Claude Code)

Usage:
  python scripts/png_to_autocad.py path/to/floorplan.png
  python scripts/png_to_autocad.py path/to/floorplan.png --save-json plan.json
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.claude import extract_plan_from_image
from scripts.lisp_writer import plan_to_lisp

LISP_OUT = "C:/temp/plan.lsp"


def main() -> None:
    parser = argparse.ArgumentParser(description="PNG floor plan → AutoCAD LISP via Claude Vision")
    parser.add_argument("png", help="Path to the floor plan PNG")
    parser.add_argument("--save-json", metavar="PATH", help="Also save extracted JSON to this path")
    parser.add_argument("--out", default=LISP_OUT, help=f"LISP output path (default: {LISP_OUT})")
    args = parser.parse_args()

    png_path = Path(args.png)
    if not png_path.exists():
        print(f"ERROR: file not found: {png_path}")
        sys.exit(1)

    # 1. Encode image
    print(f"Reading {png_path.name} ...")
    with open(png_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    # 2. Claude Vision → JSON (single call)
    print("Sending to Claude Vision...")
    plan = extract_plan_from_image(image_b64)
    room_count = len(plan.get("rooms", []))
    door_count = sum(len(r.get("doors", [])) for r in plan.get("rooms", []))
    window_count = sum(len(r.get("windows", [])) for r in plan.get("rooms", []))
    print(f"Extracted: {room_count} rooms, {door_count} doors, {window_count} windows")
    print(f"Model: {plan.get('model', 'unknown')}")

    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump(plan, f, indent=2)
        print(f"JSON saved: {args.save_json}")

    # 3. JSON → LISP
    print("Generating LISP...")
    lisp = plan_to_lisp(plan)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(lisp)
    print(f"LISP written: {out_path}")

    # 4. Instructions
    print()
    print("=" * 50)
    print("To draw in AutoCAD, run from Claude Code:")
    print(f'  MCP: system → execute_lisp: (load "{args.out}")')
    print()
    print("Or in AutoCAD command line:")
    print(f'  (load "{args.out}")')
    print("=" * 50)


if __name__ == "__main__":
    main()
