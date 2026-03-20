"""
debug_pipeline.py — Exhaustive raster-to-vector pipeline debugger.

Traces every stage and saves intermediate images so you can see exactly
where detection breaks down.

Usage:
    python scripts/debug_pipeline.py backend/data/whitestone-v2.png
    python scripts/debug_pipeline.py path/to/plan.png --out debug_out/
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("image", help="Path to floor plan PNG/JPG")
    p.add_argument("--out", default="debug_out", help="Output folder for debug images")
    p.add_argument("--backend", default="auto",
                   choices=["auto", "heuristic", "cubicasa"],
                   help="Which backend to test")
    return p.parse_args()


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def save(path: Path, img: np.ndarray, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    print(f"  [IMG] {path.name}  ({img.shape[1]}x{img.shape[0]})")

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def ok(msg):  print(f"  [OK] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def err(msg):  print(f"  [ERR] {msg}")
def info(msg): print(f"  [   ] {msg}")


def draw_walls(img_bgr: np.ndarray, walls: list[dict]) -> np.ndarray:
    vis = img_bgr.copy()
    for w in walls:
        pl = w.get("polyline", [])
        if len(pl) == 2:
            p0 = (int(pl[0]["x"]), int(pl[0]["y"]))
            p1 = (int(pl[1]["x"]), int(pl[1]["y"]))
            color = (0, 255, 0) if w.get("is_exterior") else (255, 100, 0)
            cv2.line(vis, p0, p1, color, 2)
    return vis

def draw_openings(img_bgr: np.ndarray, openings: list[dict]) -> np.ndarray:
    vis = img_bgr.copy()
    for op in openings:
        pos = op.get("position")
        if pos is None:
            continue
        cx = int(pos["x"])
        cy = int(pos["y"])
        span = int(op.get("span", 20))
        color = (0, 0, 255) if op["kind"] == "door" else (255, 0, 0)
        cv2.rectangle(vis, (cx - span//2, cy - span//2), (cx + span//2, cy + span//2), color, 2)
        cv2.putText(vis, op["kind"][0].upper(), (cx - 6, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return vis


# ─── STAGE 1: LOAD IMAGE ─────────────────────────────────────────────────────

def stage_load(image_path: Path) -> tuple[np.ndarray, str]:
    section("STAGE 1 — Load image")
    if not image_path.exists():
        err(f"File not found: {image_path}")
        sys.exit(1)
    img = cv2.imread(str(image_path))
    if img is None:
        err(f"cv2.imread failed: {image_path}")
        sys.exit(1)
    h, w = img.shape[:2]
    channels = img.shape[2] if len(img.shape) == 3 else 1
    ok(f"Loaded {w}x{h}, {channels} channels")

    # Check pixel value stats
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if channels > 1 else img
    dark_px = int(np.sum(gray < 128))
    light_px = int(np.sum(gray >= 128))
    dark_pct = dark_px / gray.size * 100
    info(f"Dark pixels (<128): {dark_px} ({dark_pct:.1f}%)  Light: {light_px} ({100-dark_pct:.1f}%)")
    if dark_pct < 2:
        warn("Very few dark pixels — image might be almost white (floor plan?)")
    elif dark_pct > 80:
        warn("Mostly dark image — might be inverted or scanned poorly")

    b64 = base64.b64encode(image_path.read_bytes()).decode()
    return img, b64


# ─── STAGE 2: BINARIZATION ───────────────────────────────────────────────────

def stage_binarize(img: np.ndarray, out: Path) -> np.ndarray:
    section("STAGE 2 — Binarization (_binarize)")

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Mirror the production code exactly
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, thresh_val = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    info(f"Otsu threshold value: {thresh_val}")

    white_px = int(np.sum(otsu > 0))
    white_pct = white_px / otsu.size * 100
    info(f"After THRESH_BINARY_INV — white pixels (=walls): {white_px} ({white_pct:.1f}%)")

    if white_pct > 50:
        warn(f"dark_ratio={white_pct:.1f}% > 50%  → production code INVERTS binary!")
        warn("  This means walls will be BLACK and background WHITE after inversion")
        warn("  Wall detection will FAIL because walls are 0 in binary")
        otsu_inverted = cv2.bitwise_not(otsu)
        save(out / "02a_binary_before_invert.png", otsu, "binary before invert")
        save(out / "02b_binary_WRONG_after_invert.png", otsu_inverted, "binary after invert (walls=black=BAD)")
        # Warn but use the pre-inversion (correct) version for downstream
        final_binary = otsu  # what SHOULD be used
    else:
        ok(f"dark_ratio={white_pct:.1f}% <= 50% → no inversion needed, walls stay white")
        final_binary = otsu

    kernel_noise = np.ones((2, 2), dtype=np.uint8)
    clean = cv2.morphologyEx(final_binary, cv2.MORPH_OPEN, kernel_noise)

    after_open = int(np.sum(clean > 0))
    info(f"After morphological open: {after_open} white pixels ({after_open/clean.size*100:.1f}%)")
    if after_open < white_px * 0.5:
        warn(f"Morphological open removed {white_px - after_open} pixels — possible over-erosion")

    save(out / "02_binary.png", clean, "binarized (walls=white)")
    return clean


# ─── STAGE 3: H/V SEGMENT EXTRACTION ─────────────────────────────────────────

def stage_segments(binary: np.ndarray, img_bgr: np.ndarray, out: Path):
    section("STAGE 3 — Morphological wall extraction")

    MIN_SEG = 20
    MIN_THICK = 2

    info(f"MIN_SEGMENT_LENGTH={MIN_SEG}px, MIN_WALL_THICKNESS={MIN_THICK}px")
    info(f"Image size: {binary.shape[1]}x{binary.shape[0]}")
    if binary.shape[1] < MIN_SEG * 5:
        warn("Image is very small — many walls may be shorter than MIN_SEGMENT_LENGTH=20")

    # H segments
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (MIN_SEG, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
    _, _, stats_h, _ = cv2.connectedComponentsWithStats(h_lines, connectivity=8)
    h_segs_raw = stats_h[1:]
    h_segs = [s for s in h_segs_raw
              if s[cv2.CC_STAT_WIDTH] >= MIN_SEG and s[cv2.CC_STAT_HEIGHT] >= MIN_THICK]

    info(f"H-segments raw: {len(h_segs_raw)}  after filter: {len(h_segs)}")
    if len(h_segs_raw) > 0 and len(h_segs) == 0:
        warn("ALL horizontal segments filtered out!")
        info("  Raw segment sizes (W x H):")
        for s in h_segs_raw[:10]:
            w = s[cv2.CC_STAT_WIDTH]; h = s[cv2.CC_STAT_HEIGHT]
            flag = "" if (w >= MIN_SEG and h >= MIN_THICK) else " ← FILTERED"
            info(f"    {w}x{h}{flag}")

    # V segments
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, MIN_SEG))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_v)
    _, _, stats_v, _ = cv2.connectedComponentsWithStats(v_lines, connectivity=8)
    v_segs_raw = stats_v[1:]
    v_segs = [s for s in v_segs_raw
              if s[cv2.CC_STAT_HEIGHT] >= MIN_SEG and s[cv2.CC_STAT_WIDTH] >= MIN_THICK]

    info(f"V-segments raw: {len(v_segs_raw)}  after filter: {len(v_segs)}")
    if len(v_segs_raw) > 0 and len(v_segs) == 0:
        warn("ALL vertical segments filtered out!")

    total = len(h_segs) + len(v_segs)
    if total == 0:
        err("ZERO wall segments detected — binarization or thresholds are the problem")
    else:
        ok(f"Total wall segments: {total} (H={len(h_segs)}, V={len(v_segs)})")

    # Visualize
    vis_h = cv2.cvtColor(h_lines, cv2.COLOR_GRAY2BGR)
    vis_v = cv2.cvtColor(v_lines, cv2.COLOR_GRAY2BGR)
    vis_both = img_bgr.copy()
    vis_both[h_lines > 0] = [0, 255, 0]
    vis_both[v_lines > 0] = [0, 0, 255]
    save(out / "03a_h_lines.png", vis_h, "horizontal wall lines")
    save(out / "03b_v_lines.png", vis_v, "vertical wall lines")
    save(out / "03c_all_walls_on_image.png", vis_both, "walls overlay (green=H, red=V)")

    return h_segs, v_segs, h_lines, v_lines


# ─── STAGE 4: WALLS → POSTPROCESS ────────────────────────────────────────────

def stage_postprocess(walls_raw: list[dict], openings_raw: list[dict],
                      structure_meta: dict, img_bgr: np.ndarray, out: Path):
    section("STAGE 4 — Postprocess filters")

    from backend.structure_postprocess import (
        _project_diagonal_walls,
        _filter_text_artifacts,
        _snap_walls,
        _snap_to_intersections,
        _merge_walls,
        build_junction_graph,
        _classify_walls_with_junctions,
        _filter_isolated_noisy_walls,
        _filter_furniture_openings,
        _deduplicate_openings,
        _limit_exterior_wall_windows,
        _anchor_openings,
        _normalize_wall_geometry,
        postprocess_structure,
        SNAP_TOLERANCE, JUNCTION_TOLERANCE, MERGE_GAP, MIN_WALL_LENGTH,
        TEXT_MAX_LENGTH, TEXT_MAX_THICKNESS,
    )
    import backend.structure_postprocess as spp

    # Re-run threshold calculation as production code does
    meta = structure_meta or {}
    if meta.get("unit") == "pixel":
        img_size = meta.get("image_size", {})
        img_w = img_size.get("width", 1000) if isinstance(img_size, dict) else 1000
        scale = max(img_w / 500.0, 1.0)
        snap_tol = 3.0 * scale
        junc_tol = 4.0 * scale
        merge_gap = 6.0 * scale
        min_len = 8.0 * scale
        text_max_len = 30.0 * scale
        text_max_thick = 4.0 * scale
    else:
        snap_tol = 4.0; junc_tol = 6.0; merge_gap = 48.0
        min_len = 12.0; text_max_len = 60.0; text_max_thick = 6.0

    info(f"Thresholds (unit={meta.get('unit', '?')}):")
    info(f"  SNAP_TOLERANCE={snap_tol:.1f}  JUNCTION_TOLERANCE={junc_tol:.1f}")
    info(f"  MERGE_GAP={merge_gap:.1f}  MIN_WALL_LENGTH={min_len:.1f}")
    info(f"  TEXT_MAX_LENGTH={text_max_len:.1f}  TEXT_MAX_THICKNESS={text_max_thick:.1f}")

    n = len(walls_raw)
    info(f"\nInput walls: {n}")

    # Step 1: diagonal projection
    projected, n_diag = _project_diagonal_walls(walls_raw)
    info(f"After diagonal projection: {len(projected)} ({n_diag} snapped to axis)")

    # Step 2: text artifact filter — show what gets removed
    spp.TEXT_MAX_LENGTH = text_max_len
    spp.TEXT_MAX_THICKNESS = text_max_thick
    filtered_text, n_text = _filter_text_artifacts(projected)
    if n_text > 0:
        warn(f"Text filter removed {n_text} walls (len<{text_max_len:.0f} AND thick<{text_max_thick:.1f})")
        # Show breakdown of removed walls
        removed_text = [w for w in projected if w not in filtered_text]
        for w in removed_text[:5]:
            pl = w["polyline"]
            dx = pl[1]["x"] - pl[0]["x"]
            dy = pl[1]["y"] - pl[0]["y"]
            length = (dx**2 + dy**2)**0.5
            thick = w.get("thickness", 0)
            info(f"    removed: len={length:.1f} thick={thick:.1f} id={w['id']}")
    else:
        ok(f"Text filter: no walls removed (all pass len>{text_max_len:.0f} OR thick>{text_max_thick:.1f})")
    info(f"After text filter: {len(filtered_text)}")

    if len(filtered_text) == 0:
        err("ALL walls removed by text filter! This is the bug.")
        return

    # Step 3: normalize + snap
    spp.SNAP_TOLERANCE = snap_tol
    try:
        norm_walls = [_normalize_wall_geometry(w) for w in filtered_text]
    except ValueError as e:
        err(f"_normalize_wall_geometry failed: {e}")
        return
    snapped = _snap_walls(norm_walls)
    info(f"After normalize+snap: {len(snapped)}")

    # Step 4: snap to intersections
    spp.JUNCTION_TOLERANCE = junc_tol
    snapped2 = _snap_to_intersections(snapped)
    info(f"After snap-to-intersections: {len(snapped2)}")

    # Step 5: merge walls
    spp.MERGE_GAP = merge_gap
    spp.MIN_WALL_LENGTH = min_len
    merged = _merge_walls(snapped2)
    info(f"After merge: {len(merged)} (gap={merge_gap:.0f}, min_len={min_len:.0f})")
    if len(merged) == 0:
        err("ALL walls lost during merge! min_len or merge_gap too aggressive.")
        # show what was there before
        for w in snapped2[:5]:
            from backend.structure_postprocess import _wall_length
            info(f"    snapped wall: len={_wall_length(w):.1f} id={w['id']}")
        return

    # Step 6: junction graph
    junctions = build_junction_graph(merged)
    info(f"Junctions: {len(junctions)}")

    # Step 7: classify exterior/interior
    classified = _classify_walls_with_junctions(merged, junctions)
    ext = sum(1 for w in classified if w.get("is_exterior"))
    info(f"Classified: {ext} exterior, {len(classified)-ext} interior")

    # Step 8: isolated noisy walls filter — show what gets removed
    filtered_noisy, n_noisy = _filter_isolated_noisy_walls(classified, junctions)
    if n_noisy > 0:
        warn(f"Isolated noisy filter removed {n_noisy} walls")
        from backend.structure_postprocess import _wall_length
        connected_ids = {wid for j in junctions for wid in j["wall_ids"]}
        removed_noisy = [w for w in classified if w not in filtered_noisy]
        for w in removed_noisy[:5]:
            length = _wall_length(w)
            thick = w.get("thickness", 0)
            ratio = thick/length if length > 0 else 999
            connected = w["id"] in connected_ids
            info(f"    removed: len={length:.1f} thick={thick:.1f} ratio={ratio:.2f} connected={connected} id={w['id']}")
    else:
        ok(f"Isolated noisy filter: no walls removed")
    info(f"After isolated noisy filter: {len(filtered_noisy)}")

    if len(filtered_noisy) == 0:
        err("ALL walls removed by isolated noisy filter!")
        return

    # Visualize wall stages
    h, w_img = img_bgr.shape[:2]
    vis = img_bgr.copy()
    for wall in filtered_noisy:
        pl = wall["polyline"]
        p0 = (int(pl[0]["x"]), int(h - pl[0]["y"]))  # note: flip Y for CubiCasa coords
        p1 = (int(pl[1]["x"]), int(h - pl[1]["y"]))
        color = (0, 200, 0) if wall.get("is_exterior") else (200, 100, 0)
        cv2.line(vis, p0, p1, color, 3)
    save(out / "04_walls_after_postprocess.png", vis, "walls after all postprocess")

    # Opening filters
    info(f"\nInput openings: {len(openings_raw)}")

    filt_openings, n_furn = _filter_furniture_openings(openings_raw, filtered_noisy)
    if n_furn:
        warn(f"Furniture filter removed {n_furn} openings")
    info(f"After furniture filter: {len(filt_openings)}")

    dedup_openings, n_dup = _deduplicate_openings(filt_openings, filtered_noisy)
    if n_dup:
        info(f"Dedup removed {n_dup} overlapping openings")
    info(f"After dedup: {len(dedup_openings)}")

    limited_openings, n_excess = _limit_exterior_wall_windows(dedup_openings, filtered_noisy)
    if n_excess:
        info(f"Window density cap removed {n_excess}")
    info(f"After window density cap: {len(limited_openings)}")

    wall_map = {w["id"]: w for w in filtered_noisy}
    review_flags: list[str] = []
    anchored, metrics = _anchor_openings(limited_openings, filtered_noisy, wall_map, review_flags)
    info(f"After anchoring: {len(anchored)} openings (filtered={metrics['filtered_opening_count']})")
    if review_flags:
        for flag in review_flags[:5]:
            warn(f"  {flag}")

    # Final summary
    section("SUMMARY")
    ok(f"Walls: {len(filtered_noisy)}")
    ok(f"Openings: {len(anchored)}")
    if len(filtered_noisy) == 0:
        err("Zero walls — DXF will be empty")
    if len(anchored) == 0:
        warn("Zero openings — no doors/windows in output")

    return filtered_noisy, anchored


# ─── STAGE 5: HEURISTIC FULL RUN ─────────────────────────────────────────────

def stage_heuristic_full(image_b64: str, img_bgr: np.ndarray, out: Path):
    section("STAGE 5 — Full heuristic infer_heuristic_structure()")

    from backend.inference_client import infer_heuristic_structure
    try:
        result = infer_heuristic_structure(image_b64)
    except Exception as e:
        err(f"infer_heuristic_structure raised: {e}")
        import traceback; traceback.print_exc()
        return

    walls = result.get("walls", [])
    openings = result.get("openings", [])
    debug = result.get("inference_debug", {})

    ok(f"Raw walls: {len(walls)}")
    ok(f"Raw openings: {len(openings)}")
    info(f"Color coded: {debug.get('color_coded')}")

    if len(walls) == 0:
        err("HEURISTIC RETURNED ZERO WALLS — problem is in binarization or segment extraction")
        return result

    # Visualize raw detections (pixel coords, no Y-flip for heuristic)
    vis = img_bgr.copy()
    h_img = img_bgr.shape[0]
    for w in walls:
        pl = w["polyline"]
        p0 = (int(pl[0]["x"]), int(pl[0]["y"]))
        p1 = (int(pl[1]["x"]), int(pl[1]["y"]))
        cv2.line(vis, p0, p1, (0, 200, 0), 2)
    for op in openings:
        pos = op.get("position")
        if pos:
            cx, cy = int(pos["x"]), int(pos["y"])
            span = int(op.get("span", 20))
            color = (0, 0, 255) if op["kind"] == "door" else (255, 0, 0)
            cv2.rectangle(vis, (cx-span//2, cy-span//2), (cx+span//2, cy+span//2), color, 2)
    save(out / "05_heuristic_raw_detections.png", vis, "raw heuristic detections")

    return result


# ─── STAGE 6: CUBICASA CHECK ─────────────────────────────────────────────────

def stage_cubicasa_check():
    section("STAGE 6 — CubiCasa availability check")

    try:
        from backend.cubicasa_inference import cubicasa_available, _WEIGHTS_PATH, available_model_variants
    except ImportError as e:
        err(f"Import error: {e}")
        return False

    info(f"Weights path: {_WEIGHTS_PATH}")
    info(f"Weights exist: {_WEIGHTS_PATH.exists()}")

    ready, reason = cubicasa_available()
    if ready:
        ok("CubiCasa IS available → this is the active backend")
    else:
        warn(f"CubiCasa NOT available: {reason}")
        warn("  → Falling back to heuristic_local")

    return ready


# ─── STAGE 7: WORKER BACKEND SELECTION ───────────────────────────────────────

def stage_backend_check():
    section("STAGE 7 — Backend selection (worker_client)")
    import os

    env_backend = os.getenv("POINTAI_INFERENCE_BACKEND")
    if env_backend:
        info(f"POINTAI_INFERENCE_BACKEND={env_backend!r} (from env)")
    else:
        info("POINTAI_INFERENCE_BACKEND not set → will auto-detect")

    try:
        from backend.worker_client import _default_backend, _backend_cache
        import backend.worker_client as wc
        wc._backend_cache = None  # reset cache for fresh check
        backend = _default_backend()
        ok(f"Selected backend: {backend!r}")
        return backend
    except Exception as e:
        err(f"Backend check failed: {e}")
        return "unknown"


# ─── STAGE 8: KNOWN BUG CHECKS ───────────────────────────────────────────────

def stage_known_bugs(img_bgr: np.ndarray, binary: np.ndarray, walls_raw: list[dict]):
    section("STAGE 8 — Known bug checklist")

    h_img, w_img = img_bgr.shape[:2]

    # BUG 1: dark_ratio inversion
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if len(img_bgr.shape) == 3 else img_bgr
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark_ratio = np.sum(otsu > 0) / otsu.size
    if dark_ratio > 0.5:
        err(f"BUG 1 TRIGGERED: dark_ratio={dark_ratio:.2%} > 50% → binary gets INVERTED")
        err("  Fix: The 'dark_ratio' variable name is misleading.")
        err("  After THRESH_BINARY_INV, white pixels = walls (dark in original).")
        err("  If wall pixels > 50% of image, re-invert makes walls black → no detection.")
    else:
        ok(f"BUG 1 (inversion): not triggered (dark_ratio={dark_ratio:.2%})")

    # BUG 2: text filter removes everything
    img_w = w_img
    scale = max(img_w / 500.0, 1.0)
    text_max_len = 30.0 * scale
    text_max_thick = 4.0 * scale
    if walls_raw:
        import math
        thin_short = 0
        for w in walls_raw:
            pl = w.get("polyline", [])
            if len(pl) == 2:
                dx = pl[1]["x"] - pl[0]["x"]
                dy = pl[1]["y"] - pl[0]["y"]
                length = math.sqrt(dx**2 + dy**2)
                thick = w.get("thickness", 4.0)
                if length < text_max_len and thick < text_max_thick:
                    thin_short += 1
        pct = thin_short / len(walls_raw) * 100 if walls_raw else 0
        if thin_short == len(walls_raw):
            err(f"BUG 2 TRIGGERED: ALL {len(walls_raw)} walls would be removed by text filter!")
            err(f"  TEXT_MAX_LENGTH={text_max_len:.0f}px, TEXT_MAX_THICKNESS={text_max_thick:.1f}px")
            err("  Fix: These thresholds are too aggressive for pixel-coordinate wall data.")
        elif thin_short > len(walls_raw) * 0.5:
            warn(f"BUG 2 PARTIAL: {thin_short}/{len(walls_raw)} walls ({pct:.0f}%) would be text-filtered")
        else:
            ok(f"BUG 2 (text filter): {thin_short}/{len(walls_raw)} walls filtered ({pct:.0f}%)")

    # BUG 3: isolated noisy filter (thickness/length ratio)
    if walls_raw:
        ratio_removed = 0
        for w in walls_raw:
            pl = w.get("polyline", [])
            if len(pl) == 2:
                import math
                dx = pl[1]["x"] - pl[0]["x"]
                dy = pl[1]["y"] - pl[0]["y"]
                length = math.sqrt(dx**2 + dy**2)
                thick = w.get("thickness", 4.0)
                if length > 0 and thick / length > 0.4:
                    ratio_removed += 1
        if ratio_removed > 0:
            warn(f"BUG 3: {ratio_removed} walls have thickness/length > 0.4 → will be removed by noisy filter")
        else:
            ok(f"BUG 3 (noisy filter ratio): no walls affected")

    # BUG 4: quality gate EPSILON
    err("BUG 4 (quality gate): quality_gate.py uses EPSILON=1e-6 for bbox coverage comparison")
    err("  Walls with coordinate residuals > 1e-6 after snapping won't count toward coverage")
    err("  bbox_sides_covered will always be 0 → 'footprint_not_reasonably_closed' always fired")
    err("  Fix: use SNAP_TOLERANCE instead of EPSILON in _compute_bbox_shell_metrics")

    # BUG 5: global variable mutation
    warn("BUG 5: postprocess_structure() mutates GLOBAL threshold variables")
    warn("  In concurrent/async FastAPI requests, thresholds can bleed between requests")
    warn("  Fix: pass thresholds as local variables instead of globals")

    # BUG 6: _find_best_wall orientation filter could drop openings
    info("BUG 6: _find_best_wall skips walls if opening.orientation != wall.orientation")
    info("  CubiCasa openings use wider bounding box dim → may mismatch wall orientation")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    image_path = Path(args.image)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\nPoint.ai — Raster-to-Vector Pipeline Debugger")
    print(f"Image: {image_path}")
    print(f"Output: {out}/")

    # S1: Load
    img_bgr, image_b64 = stage_load(image_path)
    h_img, w_img = img_bgr.shape[:2]
    save(out / "01_input.png", img_bgr, "input image")

    # S6: CubiCasa check (do early to know backend)
    cubicasa_ready = stage_cubicasa_check()

    # S7: Backend selection
    active_backend = stage_backend_check()

    # S2: Binarization
    binary = stage_binarize(img_bgr, out)

    # S3: Segment extraction
    h_segs, v_segs, h_lines, v_lines = stage_segments(binary, img_bgr, out)

    # Build raw walls for bug analysis
    from backend.inference_client import _segments_to_walls, _extract_h_segments, _extract_v_segments
    h_seg_dicts = _extract_h_segments(binary)
    v_seg_dicts = _extract_v_segments(binary)
    walls_raw = _segments_to_walls(h_seg_dicts, v_seg_dicts)

    # S8: Known bugs
    stage_known_bugs(img_bgr, binary, walls_raw)

    # S5: Full heuristic run
    heuristic_result = stage_heuristic_full(image_b64, img_bgr, out)

    # S4: Postprocess
    if heuristic_result and heuristic_result.get("walls"):
        structure_meta = heuristic_result.get("structure_meta", {})
        stage_postprocess(
            heuristic_result["walls"],
            heuristic_result.get("openings", []),
            structure_meta,
            img_bgr,
            out,
        )
    else:
        err("Skipping postprocess — no raw walls from heuristic")

    section("DEBUG COMPLETE")
    print(f"\nAll debug images saved to: {out}/")
    print("Files:")
    for f in sorted(out.iterdir()):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
