"""
mitunet_inference.py — MitUNet wall-only segmentation inference.

Uses the MitUNet architecture (MiT-b4 encoder + UNet decoder + scSE attention)
from the paper "Enhancing Floor Plan Recognition" (2025).
Produces binary wall masks, then extracts wall segments via morphology + HoughLines.
"""
from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any

import math

import cv2
import numpy as np

from .provenance import build_code_provenance, build_file_provenance, utc_now_iso

MITUNET_BACKEND = "mitunet_local"
MITUNET_MASK_REGIONS_DXF_MODE = "mask_regions"
MAX_MITUNET_REGION_WALL_THICKNESS = 6.0
MITUNET_MODEL_NAME = "MitUNet MiT-B4 UNet scSE"

_WEIGHTS_PATH = Path(r"C:\Users\lucas\OneDrive\Escritorio\pesos\mitunet_finetune_a6_mit_b4_tversky_8864_28E.pth")
_IMAGE_SIZE = 512
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406])
_IMAGENET_STD = np.array([0.229, 0.224, 0.225])

_model = None
_device = None


def mitunet_available() -> tuple[bool, str | None]:
    if not _WEIGHTS_PATH.exists():
        return False, f"No weights found: {_WEIGHTS_PATH}"
    try:
        import torch
        import segmentation_models_pytorch as smp
        return True, None
    except ImportError as e:
        return False, str(e)


def _load_model():
    global _model, _device
    if _model is not None:
        return _model, _device

    import torch
    import segmentation_models_pytorch as smp

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Build MitUNet architecture
    aux = smp.Segformer(encoder_name="mit_b4", encoder_weights=None)
    model = smp.Unet(
        encoder_name="mit_b4",
        encoder_weights=None,
        in_channels=3,
        classes=1,
        decoder_attention_type="scse",
    )
    model.encoder = aux.encoder

    state_dict = torch.load(str(_WEIGHTS_PATH), map_location=_device, weights_only=False)
    model.load_state_dict(state_dict)
    model.to(_device)
    model.eval()

    _model = model
    print(f"[MitUNet] Model loaded on {_device}")
    return _model, _device


def _preprocess(image_bgr: np.ndarray) -> "torch.Tensor":
    import torch

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(image_rgb, (_IMAGE_SIZE, _IMAGE_SIZE))
    tensor = resized.astype(np.float32) / 255.0
    tensor = (tensor - _IMAGENET_MEAN) / _IMAGENET_STD
    tensor = torch.from_numpy(tensor.transpose(2, 0, 1)).float().unsqueeze(0)
    return tensor


def _predict_wall_mask(image_bgr: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Run MitUNet and return binary wall mask at original resolution."""
    import torch

    model, device = _load_model()
    h_orig, w_orig = image_bgr.shape[:2]

    tensor = _preprocess(image_bgr).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)
        mask = (probs > threshold).float()

    result = mask.squeeze().cpu().numpy()
    result_uint8 = (result * 255).astype(np.uint8)
    return cv2.resize(result_uint8, (w_orig, h_orig))


def _extract_walls_from_mask(wall_mask: np.ndarray, h: int, w: int) -> list[dict]:
    """Extract wall polylines from binary mask using contours + Douglas-Peucker.

    Pipeline:
    1. Morphological cleanup (close small gaps)
    2. findContours (external + internal boundaries)
    3. approxPolyDP (Douglas-Peucker simplification)
    4. Orthogonal regularization (snap near-90° angles to exact 90°)
    5. Flip Y for DXF coordinate system
    """
    walls = []
    wall_id = 0

    # 1. Clean mask — close small gaps, remove tiny noise
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    cleaned = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)
    # Remove small noise blobs
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel_open, iterations=1)

    min_area = max(100, (h * w) // 5000)  # minimum wall area in pixels

    # 2. Find contours — RETR_LIST gets all contours (external + holes)
    contours, _ = cv2.findContours(cleaned, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter < 20:
            continue

        # 3. Douglas-Peucker simplification — epsilon controls smoothing
        epsilon = max(2.0, perimeter * 0.008)  # low epsilon = keep detail
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        if len(approx) < 3:
            continue

        # 4. Orthogonal regularization — snap near-90° corners to exact 90°
        points = approx.reshape(-1, 2).tolist()
        regularized = _orthogonal_regularize(points)

        # 5. Convert to polyline segments (flip Y for DXF)
        dxf_points = [[int(p[0]), int(h - p[1])] for p in regularized]

        # Convert polyline to individual 2-point axis-aligned segments
        # (required by plan_parser / structure_postprocess)
        for j in range(len(dxf_points)):
            p1 = dxf_points[j]
            p2 = dxf_points[(j + 1) % len(dxf_points)]

            dx = abs(p2[0] - p1[0])
            dy = abs(p2[1] - p1[1])
            seg_len = max(dx, dy)

            if seg_len < 5:
                continue  # skip tiny segments

            # Determine orientation and force axis-aligned
            if dx >= dy:  # horizontal
                mid_y = (p1[1] + p2[1]) // 2
                walls.append({
                    "id": f"mu-wall-{wall_id:04d}",
                    "polyline": [[p1[0], mid_y], [p2[0], mid_y]],
                    "orientation": "horizontal",
                    "type": "wall",
                })
            else:  # vertical
                mid_x = (p1[0] + p2[0]) // 2
                walls.append({
                    "id": f"mu-wall-{wall_id:04d}",
                    "polyline": [[mid_x, p1[1]], [mid_x, p2[1]]],
                    "orientation": "vertical",
                    "type": "wall",
                })
            wall_id += 1

    # Merge nearby collinear segments
    walls = _merge_collinear_walls(walls, h)

    return walls


def _merge_collinear_walls(walls: list[dict], img_h: int, gap: int = 15, dist: int = 8) -> list[dict]:
    """Merge wall segments that are collinear and close together."""
    h_walls = [w for w in walls if w["orientation"] == "horizontal"]
    v_walls = [w for w in walls if w["orientation"] == "vertical"]
    merged = []
    wall_id = 0

    # Merge horizontal
    h_walls.sort(key=lambda w: (w["polyline"][0][1], w["polyline"][0][0]))
    merged_h: list[list[int]] = []  # [x1, y, x2, y]
    for w in h_walls:
        p = w["polyline"]
        x1, y1 = min(p[0][0], p[1][0]), p[0][1]
        x2 = max(p[0][0], p[1][0])
        was_merged = False
        for i, m in enumerate(merged_h):
            if abs(y1 - m[1]) < dist and (x1 <= m[2] + gap and x2 >= m[0] - gap):
                merged_h[i] = [min(x1, m[0]), (y1 + m[1]) // 2, max(x2, m[2]), (y1 + m[1]) // 2]
                was_merged = True
                break
        if not was_merged:
            merged_h.append([x1, y1, x2, y1])

    for seg in merged_h:
        merged.append({
            "id": f"mu-wall-{wall_id:04d}",
            "polyline": [[seg[0], seg[1]], [seg[2], seg[3]]],
            "orientation": "horizontal",
            "type": "wall",
        })
        wall_id += 1

    # Merge vertical
    v_walls.sort(key=lambda w: (w["polyline"][0][0], w["polyline"][0][1]))
    merged_v: list[list[int]] = []  # [x, y1, x, y2]
    for w in v_walls:
        p = w["polyline"]
        x1 = p[0][0]
        y1, y2 = min(p[0][1], p[1][1]), max(p[0][1], p[1][1])
        was_merged = False
        for i, m in enumerate(merged_v):
            if abs(x1 - m[0]) < dist and (y1 <= m[3] + gap and y2 >= m[1] - gap):
                merged_v[i] = [(x1 + m[0]) // 2, min(y1, m[1]), (x1 + m[0]) // 2, max(y2, m[3])]
                was_merged = True
                break
        if not was_merged:
            merged_v.append([x1, y1, x1, y2])

    for seg in merged_v:
        merged.append({
            "id": f"mu-wall-{wall_id:04d}",
            "polyline": [[seg[0], seg[1]], [seg[2], seg[3]]],
            "orientation": "vertical",
            "type": "wall",
        })
        wall_id += 1

    return merged


def _orthogonal_regularize(points: list[list[int]], angle_thresh: float = 15.0) -> list[list[int]]:
    """Snap near-orthogonal edges to exact H/V alignment.

    For each consecutive pair of points, if the angle is within
    `angle_thresh` degrees of horizontal or vertical, snap it.
    """
    if len(points) < 2:
        return points

    result = [points[0]]
    for i in range(1, len(points)):
        px, py = result[-1]
        cx, cy = points[i]
        dx = cx - px
        dy = cy - py

        if abs(dx) < 1 and abs(dy) < 1:
            continue  # skip duplicate points

        angle = abs(np.degrees(np.arctan2(dy, dx)))

        # Near horizontal (0° or 180°)
        if angle < angle_thresh or angle > (180 - angle_thresh):
            cy = py  # force same Y
        # Near vertical (90°)
        elif abs(angle - 90) < angle_thresh:
            cx = px  # force same X

        result.append([int(cx), int(cy)])

    return result


def infer_mitunet(image_b64: str, **kwargs) -> dict[str, Any]:
    """Run MitUNet inference on a base64-encoded image."""
    t0 = time.time()

    # Decode image (strip data URI prefix if present)
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    # Fix padding
    missing_padding = len(image_b64) % 4
    if missing_padding:
        image_b64 += "=" * (4 - missing_padding)
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    image_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Could not decode image")

    h, w = image_bgr.shape[:2]

    # Get wall mask
    t_model = time.time()
    wall_mask = _predict_wall_mask(image_bgr)
    t_model = time.time() - t_model

    # Generate overlay from mask (image coordinates, before any flip)
    overlay = image_bgr.copy()
    overlay[wall_mask > 127] = [0, 0, 200]  # dark red on walls
    blended = cv2.addWeighted(image_bgr, 0.6, overlay, 0.4, 0)
    _, overlay_png = cv2.imencode(".png", blended)
    overlay_b64 = base64.b64encode(overlay_png.tobytes()).decode("ascii")

    # Extract wall segments (with Y-flip for DXF)
    t_post = time.time()
    walls = _extract_walls_from_mask(wall_mask, h, w)
    t_post = time.time() - t_post

    total = time.time() - t0
    wall_pct = (wall_mask > 127).sum() / (h * w) * 100
    print(f"[MitUNet] model={t_model:.2f}s post={t_post:.2f}s total={total:.2f}s walls={len(walls)} ({wall_pct:.1f}% pixels)")

    return {
        "walls": walls,
        "openings": [],
        "rooms": [],
        "source": MITUNET_BACKEND,
        "inference_debug": {
            "backend": MITUNET_BACKEND,
            "debug_overlay_b64": f"data:image/png;base64,{overlay_b64}",
            "model_variant": "mitunet",
            "wall_pixel_pct": round(wall_pct, 1),
        },
        "_wall_mask": wall_mask,
        "_image_shape": (h, w),
    }


# ---------------------------------------------------------------------------
# Template path
# ---------------------------------------------------------------------------
_TEMPLATE_PATH = Path(__file__).resolve().parent / "data" / "plans" / "MARCAREGISTRADA.dxf"

# Plan drawing area inside the template (left of title block)
_PLAN_X1 = 40
_PLAN_Y1 = 30
_PLAN_X2 = 1530
_PLAN_Y2 = 1080


def build_mitunet_provenance(*, dxf_mode: str = MITUNET_MASK_REGIONS_DXF_MODE) -> dict[str, Any]:
    return {
        "captured_at_utc": utc_now_iso(),
        "backend": MITUNET_BACKEND,
        "model_variant": "mitunet",
        "model_name": MITUNET_MODEL_NAME,
        "dxf_mode": dxf_mode,
        "region_contract_version": "mitunet_region_plan_v1",
        "max_region_wall_thickness": float(MAX_MITUNET_REGION_WALL_THICKNESS),
        "code": build_code_provenance(),
        "weights": build_file_provenance(_WEIGHTS_PATH),
        "template": build_file_provenance(_TEMPLATE_PATH),
    }


def generate_mitunet_dxf(infer_result: dict[str, Any], out_path: str,
                         annotations: list[dict] | None = None) -> int:
    """Legacy entrypoint kept as a compatibility wrapper.

    The real MitUNet DXF path is now:
    raw mask -> region_plan -> generate_mitunet_region_dxf
    """
    region_plan = build_mitunet_region_plan(infer_result, annotations=annotations)
    rect_count, _ = generate_mitunet_region_dxf(region_plan, out_path, annotations=annotations)
    return rect_count

    import ezdxf

    wall_mask = infer_result["_wall_mask"]
    h, w = infer_result["_image_shape"]

    # Load template or create blank doc
    if _TEMPLATE_PATH.exists():
        doc = ezdxf.readfile(str(_TEMPLATE_PATH))
    else:
        doc = ezdxf.new("R2010")

    msp = doc.modelspace()

    # Ensure WALLS layer exists
    if "WALLS" not in doc.layers:
        doc.layers.add("WALLS", color=7)

    # Clean mask
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    cleaned = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    # Apply eraser zones — black out areas the user marked for deletion
    if annotations:
        for ann in annotations:
            if ann.get("type") == "eraser":
                ex1 = max(0, int(ann["x1"]))
                ey1 = max(0, int(ann["y1"]))
                ex2 = min(w, int(ann["x2"]))
                ey2 = min(h, int(ann["y2"]))
                cleaned[ey1:ey2, ex1:ex2] = 0

    min_len = max(8, min(h, w) // 40)

    # Scale to fit inside template
    plan_w = _PLAN_X2 - _PLAN_X1
    plan_h = _PLAN_Y2 - _PLAN_Y1
    img_aspect = w / h
    plan_aspect = plan_w / plan_h

    if img_aspect > plan_aspect:
        scale = plan_w / w
        offset_x = _PLAN_X1
        offset_y = _PLAN_Y1 + (plan_h - h * scale) / 2
    else:
        scale = plan_h / h
        offset_x = _PLAN_X1 + (plan_w - w * scale) / 2
        offset_y = _PLAN_Y1

    def _img_to_dxf(ix: int, iy: int) -> tuple[float, float]:
        """Convert image coords to DXF coords (scale + offset + flip Y)."""
        dx = ix * scale + offset_x
        dy = (h - iy) * scale + offset_y
        return dx, dy

    rect_count = 0
    WALL_THIN = 0.4

    # --- Collect all wall rects (in DXF coords) ---
    # Each rect = (x_lo, y_lo, x_hi, y_hi, orientation)
    h_rects: list[list[float]] = []
    v_rects: list[list[float]] = []

    # H walls
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1))
    h_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, h_kernel)
    num_h, _, stats_h, _ = cv2.connectedComponentsWithStats(h_mask, connectivity=8)
    for i in range(1, num_h):
        x = stats_h[i, cv2.CC_STAT_LEFT]
        y = stats_h[i, cv2.CC_STAT_TOP]
        cw = stats_h[i, cv2.CC_STAT_WIDTH]
        ch = stats_h[i, cv2.CC_STAT_HEIGHT]
        if cw < min_len or ch < 2:
            continue
        # Skip if too square (not a wall shape) — walls are elongated
        if ch > 0 and cw / ch < 2.5:
            continue
        trim = ch * (1 - WALL_THIN) / 2
        y_s = y + trim
        ch_s = ch - 2 * trim
        x1d, y1d = _img_to_dxf(x, y_s + ch_s)
        x2d, y2d = _img_to_dxf(x + cw, y_s)
        h_rects.append([min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)])

    # V walls
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len))
    v_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, v_kernel)
    num_v, _, stats_v, _ = cv2.connectedComponentsWithStats(v_mask, connectivity=8)
    for i in range(1, num_v):
        x = stats_v[i, cv2.CC_STAT_LEFT]
        y = stats_v[i, cv2.CC_STAT_TOP]
        cw = stats_v[i, cv2.CC_STAT_WIDTH]
        ch = stats_v[i, cv2.CC_STAT_HEIGHT]
        if ch < min_len or cw < 2:
            continue
        # Skip if too square (not a wall shape)
        if cw > 0 and ch / cw < 2.5:
            continue
        trim = cw * (1 - WALL_THIN) / 2
        x_s = x + trim
        cw_s = cw - 2 * trim
        x1d, y1d = _img_to_dxf(x_s, y + ch)
        x2d, y2d = _img_to_dxf(x_s + cw_s, y)
        v_rects.append([min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)])

    # --- Trim overlapping junctions ---
    # Algorithm based on "Raster to Rectangles" (2024):
    # For each H-V pair that overlaps, check if the wall ENDS inside the other
    # (T-junction) vs PASSES THROUGH (X-junction).
    # T-junction: trim the ending wall to meet the edge of the other.
    # X-junction: leave both as-is (wall passes through).
    TOL = 2.0
    V_WIDTH_MARGIN = 1.3  # if H extends past V center + margin*V_width, it's passing through

    for hr in h_rects:
        hx1, hy1, hx2, hy2 = hr
        h_cy = (hy1 + hy2) / 2

        for vr in v_rects:
            vx1, vy1, vx2, vy2 = vr
            v_cx = (vx1 + vx2) / 2
            v_w = vx2 - vx1

            # Check if H overlaps V vertically
            if not (vy1 - TOL <= h_cy <= vy2 + TOL):
                continue
            # Check if H overlaps V horizontally
            if not (hx1 < vx2 and hx2 > vx1):
                continue

            # H right end inside V zone (T-junction from left)
            if vx1 - TOL < hx2 < vx2 + v_w * V_WIDTH_MARGIN:
                hr[2] = vx2  # extend H right to V right edge (clean T)
            # H left end inside V zone (T-junction from right)
            if vx1 - v_w * V_WIDTH_MARGIN < hx1 < vx2 + TOL:
                hr[0] = vx1  # extend H left to V left edge (clean T)

    for vr in v_rects:
        vx1, vy1, vx2, vy2 = vr
        v_cx = (vx1 + vx2) / 2

        for hr in h_rects:
            hx1, hy1, hx2, hy2 = hr
            h_cy = (hy1 + hy2) / 2
            h_h = hy2 - hy1

            # Check if V overlaps H horizontally
            if not (hx1 - TOL <= v_cx <= hx2 + TOL):
                continue
            # Check if V overlaps H vertically
            if not (vy1 < hy2 and vy2 > hy1):
                continue

            # V top end inside H zone (T-junction from below)
            if hy1 - TOL < vy2 < hy2 + h_h * V_WIDTH_MARGIN:
                vr[3] = hy2  # extend V top to H top edge
            # V bottom end inside H zone (T-junction from above)
            if hy1 - h_h * V_WIDTH_MARGIN < vy1 < hy2 + TOL:
                vr[1] = hy1  # extend V bottom to H bottom edge

    # --- Draw all rects + compute median thickness ---
    model_thicknesses: list[float] = []
    for r in h_rects + v_rects:
        x1, y1, x2, y2 = r
        if abs(x2 - x1) < 1 or abs(y2 - y1) < 1:
            continue
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
        poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7})
        poly.close()
        hatch = msp.add_hatch(color=7, dxfattribs={"layer": "WALLS"})
        hatch.paths.add_polyline_path(pts, is_closed=True)
        rect_count += 1
        model_thicknesses.append(min(abs(x2 - x1), abs(y2 - y1)))

    # Median wall thickness from model rects (annotations should match)
    if model_thicknesses:
        model_thicknesses.sort()
        _mid = len(model_thicknesses) // 2
        ann_wall_thickness = model_thicknesses[_mid] if len(model_thicknesses) % 2 else (model_thicknesses[_mid - 1] + model_thicknesses[_mid]) / 2
    else:
        ann_wall_thickness = 4.0

    # --- Draw user annotations (walls/doors/windows) ---
    if annotations:
        # Ensure layers exist
        if "DOORS" not in doc.layers:
            doc.layers.add("DOORS", color=157)
        if "WINS" not in doc.layers:
            doc.layers.add("WINS", color=121)

        # The annotations are in canvas pixel coordinates (same as overlay image)
        # We need to figure out the overlay image size to map correctly
        # The overlay matches the original image size (h, w)
        for ann in annotations:
            ann_type = ann.get("type", "wall")
            if ann_type == "eraser":
                continue  # eraser zones already applied to mask above
            # Canvas coords → image coords (canvas matches overlay which matches image)
            ax1, ay1 = ann["x1"], ann["y1"]
            ax2, ay2 = ann["x2"], ann["y2"]

            # But canvas may be scaled from original image size
            # The overlay is rendered at original image size, canvas displays it scaled
            # Annotations are in canvas pixel coords which map to image coords

            # Convert to DXF coords
            dx1, dy1 = _img_to_dxf(int(ax1), int(ay1))
            dx2, dy2 = _img_to_dxf(int(ax2), int(ay2))

            if ann_type == "wall":
                # Wall: rectangle with hatch (same as model walls)
                # Determine if H or V
                adx = abs(dx2 - dx1)
                ady = abs(dy2 - dy1)
                thickness = ann_wall_thickness  # match model wall thickness (median)
                if adx >= ady:  # horizontal
                    y_mid = (dy1 + dy2) / 2
                    x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                    pts = [(x_lo, y_mid - thickness/2), (x_hi, y_mid - thickness/2),
                           (x_hi, y_mid + thickness/2), (x_lo, y_mid + thickness/2),
                           (x_lo, y_mid - thickness/2)]
                else:  # vertical
                    x_mid = (dx1 + dx2) / 2
                    y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                    pts = [(x_mid - thickness/2, y_lo), (x_mid + thickness/2, y_lo),
                           (x_mid + thickness/2, y_hi), (x_mid - thickness/2, y_hi),
                           (x_mid - thickness/2, y_lo)]
                poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7})
                poly.close()
                hatch = msp.add_hatch(color=7, dxfattribs={"layer": "WALLS"})
                hatch.paths.add_polyline_path(pts, is_closed=True)
                rect_count += 1

            elif ann_type == "door":
                # Door: user draws line from hinge to end of door
                # startPt = hinge (bisagra, encastrada en pared)
                # endPt = where door ends when closed
                # swing direction = which side the door opens to (perpendicular)
                slab = 1.5
                swing = ann.get("swing", "up")
                DA = {"layer": "DOORS", "color": 157}

                # User draws line across the GAP between walls
                # P1 = hinge side (start), P2 = other end of gap
                # Swing direction = which side the door opens INTO (the room)
                #
                # The SLAB goes perpendicular to the gap, from hinge INTO the room
                # Length of slab = width of gap = door width
                # The ARC sweeps from slab end back to the gap
                hx, hy = dx1, dy1  # hinge (at gap edge, against wall)
                ex, ey = dx2, dy2  # other end of gap

                # Gap direction vector
                gap_dx = ex - hx
                gap_dy = ey - hy
                door_width = math.hypot(gap_dx, gap_dy)
                if door_width < 2:
                    continue

                # Normalize gap direction
                gx = gap_dx / door_width
                gy = gap_dy / door_width

                # Swing direction = absolute direction, not relative to gap
                if swing == "up":
                    sx, sy = 0, 1
                elif swing == "down":
                    sx, sy = 0, -1
                elif swing == "right":
                    sx, sy = 1, 0
                else:  # left
                    sx, sy = -1, 0

                # Slab: from hinge, goes perpendicular INTO the room
                slab_end_x = hx + sx * door_width
                slab_end_y = hy + sy * door_width

                # Slab line 1 (main)
                msp.add_line((hx, hy), (slab_end_x, slab_end_y), dxfattribs=DA)
                # Slab line 2 (offset by slab thickness along gap direction)
                msp.add_line((hx + gx * slab, hy + gy * slab),
                             (slab_end_x + gx * slab, slab_end_y + gy * slab), dxfattribs=DA)

                # Arc: center at hinge, from slab direction to gap direction
                slab_angle = math.degrees(math.atan2(sy, sx))
                gap_angle = math.degrees(math.atan2(gy, gx))

                # Normalize to 0-360
                if slab_angle < 0: slab_angle += 360
                if gap_angle < 0: gap_angle += 360

                a1 = min(slab_angle, gap_angle)
                a2 = max(slab_angle, gap_angle)
                if a2 - a1 > 180:
                    a1, a2 = a2, a1 + 360

                msp.add_arc((hx, hy), door_width, a1, a2, dxfattribs=DA)

            elif ann_type == "window":
                # Window: 3 parallel lines + 2 end caps + sill (5" offset)
                adx = abs(dx2 - dx1)
                ady = abs(dy2 - dy1)

                if adx >= ady:  # horizontal window
                    x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                    y_mid = (dy1 + dy2) / 2
                    for off in [0, -1, -2]:
                        msp.add_line((x_lo, y_mid + off), (x_hi, y_mid + off),
                                     dxfattribs={"layer": "WINS", "color": 121})
                    # End caps
                    msp.add_line((x_lo, y_mid - 1), (x_lo, y_mid - 2),
                                 dxfattribs={"layer": "WINS", "color": 121})
                    msp.add_line((x_hi, y_mid - 1), (x_hi, y_mid - 2),
                                 dxfattribs={"layer": "WINS", "color": 121})
                    # Sill
                    msp.add_line((x_lo, y_mid - 5), (x_hi, y_mid - 5),
                                 dxfattribs={"layer": "WINS", "color": 121})
                else:  # vertical window
                    y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                    x_mid = (dx1 + dx2) / 2
                    for off in [0, -1, 1]:
                        msp.add_line((x_mid + off, y_lo), (x_mid + off, y_hi),
                                     dxfattribs={"layer": "WINS", "color": 121})
                    # End caps
                    msp.add_line((x_mid - 1, y_lo), (x_mid, y_lo),
                                 dxfattribs={"layer": "WINS", "color": 121})
                    msp.add_line((x_mid - 1, y_hi), (x_mid, y_hi),
                                 dxfattribs={"layer": "WINS", "color": 121})
                    # Sill
                    msp.add_line((x_mid + 5, y_lo), (x_mid + 5, y_hi),
                                 dxfattribs={"layer": "WINS", "color": 121})

    doc.saveas(out_path)
    return rect_count


def _prepare_mitunet_wall_mask_for_regions(
    wall_mask: np.ndarray,
    *,
    image_shape: tuple[int, int],
    annotations: list[dict] | None = None,
) -> np.ndarray:
    h, w = image_shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    cleaned = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
    )

    if annotations:
        for ann in annotations:
            if ann.get("type") != "eraser":
                continue
            ex1 = max(0, int(ann["x1"]))
            ey1 = max(0, int(ann["y1"]))
            ex2 = min(w, int(ann["x2"]))
            ey2 = min(h, int(ann["y2"]))
            cleaned[ey1:ey2, ex1:ex2] = 0

    return cleaned


def _binary_mask_bbox(mask: np.ndarray) -> dict[str, int] | None:
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return {
        "x1": int(x),
        "y1": int(y),
        "x2": int(x + w),
        "y2": int(y + h),
    }


def _summarize_binary_mask(mask: np.ndarray) -> dict[str, Any]:
    binary = (mask > 0).astype(np.uint8)
    component_count = 0
    largest_component_area = 0
    if binary.size > 0:
        num_components, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        component_count = max(0, int(num_components - 1))
        if component_count > 0:
            largest_component_area = int(stats[1:, cv2.CC_STAT_AREA].max())

    nonzero_pixel_count = int(np.count_nonzero(binary))
    return {
        "shape": {"height": int(binary.shape[0]), "width": int(binary.shape[1])},
        "nonzero_pixel_count": nonzero_pixel_count,
        "coverage_ratio": float(nonzero_pixel_count / float(binary.size)) if binary.size else 0.0,
        "component_count": component_count,
        "largest_component_area": largest_component_area,
        "bbox": _binary_mask_bbox(binary),
    }


def _rect_bounds_dict(rect: list[float]) -> dict[str, float]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }


def _rect_stage_entry(
    rect: list[float],
    *,
    orientation: str,
    rect_id: str,
) -> dict[str, Any]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    return {
        "id": rect_id,
        "orientation": orientation,
        "bounds": _rect_bounds_dict(rect),
        "length": float(max(abs(x2 - x1), abs(y2 - y1))),
        "thickness": float(min(abs(x2 - x1), abs(y2 - y1))),
    }


def _resolve_mitunet_plan_transform(image_shape: tuple[int, int]) -> dict[str, float]:
    h, w = image_shape
    plan_w = _PLAN_X2 - _PLAN_X1
    plan_h = _PLAN_Y2 - _PLAN_Y1
    img_aspect = w / h
    plan_aspect = plan_w / plan_h

    if img_aspect > plan_aspect:
        scale = plan_w / w
        offset_x = _PLAN_X1
        offset_y = _PLAN_Y1 + (plan_h - h * scale) / 2
    else:
        scale = plan_h / h
        offset_x = _PLAN_X1 + (plan_w - w * scale) / 2
        offset_y = _PLAN_Y1

    return {
        "scale": float(scale),
        "offset_x": float(offset_x),
        "offset_y": float(offset_y),
        "plan_x1": float(_PLAN_X1),
        "plan_y1": float(_PLAN_Y1),
        "plan_x2": float(_PLAN_X2),
        "plan_y2": float(_PLAN_Y2),
    }


def _mitunet_region_img_to_dxf(
    ix: float,
    iy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[float, float]:
    h, _ = image_shape
    dx = ix * transform["scale"] + transform["offset_x"]
    dy = (h - iy) * transform["scale"] + transform["offset_y"]
    return dx, dy


def _mitunet_region_dxf_to_img(
    dx: float,
    dy: float,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[float, float]:
    h, _ = image_shape
    scale = float(transform.get("scale", 1.0) or 1.0)
    offset_x = float(transform.get("offset_x", 0.0) or 0.0)
    offset_y = float(transform.get("offset_y", 0.0) or 0.0)
    ix = (dx - offset_x) / scale
    iy = h - ((dy - offset_y) / scale)
    return ix, iy


def regions_to_wall_annotations(
    region_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert region plan wall regions to image-space wall annotations."""
    meta = region_plan.get("meta") or {}
    image_shape_meta = meta.get("image_shape") or {}
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    transform = meta.get("transform") or {}
    if image_shape[0] <= 0 or image_shape[1] <= 0:
        return []

    annotations: list[dict[str, Any]] = []
    for region in region_plan.get("regions", []):
        bounds = region.get("bounds") or {}
        x1 = float(bounds.get("x1", 0))
        y1 = float(bounds.get("y1", 0))
        x2 = float(bounds.get("x2", 0))
        y2 = float(bounds.get("y2", 0))
        orientation = region.get("orientation", "horizontal")

        # Region center line in DXF coords
        if orientation == "horizontal":
            mid_y = (y1 + y2) / 2
            dxf_start, dxf_end = (x1, mid_y), (x2, mid_y)
        else:
            mid_x = (x1 + x2) / 2
            dxf_start, dxf_end = (mid_x, y1), (mid_x, y2)

        # Convert to image coords
        ix1, iy1 = _mitunet_region_dxf_to_img(
            dxf_start[0], dxf_start[1],
            image_shape=image_shape, transform=transform,
        )
        ix2, iy2 = _mitunet_region_dxf_to_img(
            dxf_end[0], dxf_end[1],
            image_shape=image_shape, transform=transform,
        )

        annotations.append({
            "type": "wall",
            "x1": round(ix1, 1),
            "y1": round(iy1, 1),
            "x2": round(ix2, 1),
            "y2": round(iy2, 1),
            "_source": "mitunet_region",
        })

    return annotations


def _collect_mitunet_region_rectangles(
    cleaned: np.ndarray,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
    h, w = image_shape
    min_len = max(8, min(h, w) // 40)
    wall_thin = 0.4
    h_rects: list[list[float]] = []
    v_rects: list[list[float]] = []
    h_components: list[dict[str, Any]] = []
    v_components: list[dict[str, Any]] = []

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1))
    h_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, h_kernel)
    num_h, _, stats_h, _ = cv2.connectedComponentsWithStats(h_mask, connectivity=8)
    for i in range(1, num_h):
        x = stats_h[i, cv2.CC_STAT_LEFT]
        y = stats_h[i, cv2.CC_STAT_TOP]
        cw = stats_h[i, cv2.CC_STAT_WIDTH]
        ch = stats_h[i, cv2.CC_STAT_HEIGHT]
        component_entry = {
            "component_index": int(i),
            "orientation": "horizontal",
            "image_bounds": {
                "x1": int(x),
                "y1": int(y),
                "x2": int(x + cw),
                "y2": int(y + ch),
            },
            "pixel_width": int(cw),
            "pixel_height": int(ch),
            "accepted": False,
        }
        if cw < min_len or ch < 2:
            component_entry["skip_reason"] = "too_short"
            h_components.append(component_entry)
            continue
        if ch > 0 and cw / ch < 2.5:
            component_entry["skip_reason"] = "insufficient_aspect_ratio"
            h_components.append(component_entry)
            continue
        trim = ch * (1 - wall_thin) / 2
        y_s = y + trim
        ch_s = ch - 2 * trim
        x1d, y1d = _mitunet_region_img_to_dxf(x, y_s + ch_s, image_shape=image_shape, transform=transform)
        x2d, y2d = _mitunet_region_img_to_dxf(x + cw, y_s, image_shape=image_shape, transform=transform)
        rect = [min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)]
        h_rects.append(rect)
        component_entry["accepted"] = True
        component_entry["dxf_bounds"] = _rect_bounds_dict(rect)
        component_entry["dxf_length"] = float(max(rect[2] - rect[0], rect[3] - rect[1]))
        component_entry["dxf_thickness"] = float(min(rect[2] - rect[0], rect[3] - rect[1]))
        h_components.append(component_entry)

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len))
    v_mask = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, v_kernel)
    num_v, _, stats_v, _ = cv2.connectedComponentsWithStats(v_mask, connectivity=8)
    for i in range(1, num_v):
        x = stats_v[i, cv2.CC_STAT_LEFT]
        y = stats_v[i, cv2.CC_STAT_TOP]
        cw = stats_v[i, cv2.CC_STAT_WIDTH]
        ch = stats_v[i, cv2.CC_STAT_HEIGHT]
        component_entry = {
            "component_index": int(i),
            "orientation": "vertical",
            "image_bounds": {
                "x1": int(x),
                "y1": int(y),
                "x2": int(x + cw),
                "y2": int(y + ch),
            },
            "pixel_width": int(cw),
            "pixel_height": int(ch),
            "accepted": False,
        }
        if ch < min_len or cw < 2:
            component_entry["skip_reason"] = "too_short"
            v_components.append(component_entry)
            continue
        if cw > 0 and ch / cw < 2.5:
            component_entry["skip_reason"] = "insufficient_aspect_ratio"
            v_components.append(component_entry)
            continue
        trim = cw * (1 - wall_thin) / 2
        x_s = x + trim
        cw_s = cw - 2 * trim
        x1d, y1d = _mitunet_region_img_to_dxf(x_s, y + ch, image_shape=image_shape, transform=transform)
        x2d, y2d = _mitunet_region_img_to_dxf(x_s + cw_s, y, image_shape=image_shape, transform=transform)
        rect = [min(x1d, x2d), min(y1d, y2d), max(x1d, x2d), max(y1d, y2d)]
        v_rects.append(rect)
        component_entry["accepted"] = True
        component_entry["dxf_bounds"] = _rect_bounds_dict(rect)
        component_entry["dxf_length"] = float(max(rect[2] - rect[0], rect[3] - rect[1]))
        component_entry["dxf_thickness"] = float(min(rect[2] - rect[0], rect[3] - rect[1]))
        v_components.append(component_entry)

    return h_rects, v_rects, {
        "min_len": float(min_len),
        "wall_thin": float(wall_thin),
        "horizontal_mask": _summarize_binary_mask(h_mask),
        "vertical_mask": _summarize_binary_mask(v_mask),
        "horizontal_components": h_components,
        "vertical_components": v_components,
        "horizontal_candidate_count": len(h_components),
        "vertical_candidate_count": len(v_components),
        "horizontal_accepted_count": sum(1 for component in h_components if component["accepted"]),
        "vertical_accepted_count": sum(1 for component in v_components if component["accepted"]),
    }


def _trim_mitunet_region_rectangles(h_rects: list[list[float]], v_rects: list[list[float]]) -> None:
    tol = 2.0
    width_margin = 1.3

    for hr in h_rects:
        hx1, hy1, hx2, hy2 = hr
        h_cy = (hy1 + hy2) / 2
        for vr in v_rects:
            vx1, vy1, vx2, vy2 = vr
            v_w = vx2 - vx1
            if not (vy1 - tol <= h_cy <= vy2 + tol):
                continue
            if not (hx1 < vx2 and hx2 > vx1):
                continue
            if vx1 - tol < hx2 < vx2 + v_w * width_margin:
                hr[2] = vx2
            if vx1 - v_w * width_margin < hx1 < vx2 + tol:
                hr[0] = vx1

    for vr in v_rects:
        vx1, vy1, vx2, vy2 = vr
        v_cx = (vx1 + vx2) / 2
        for hr in h_rects:
            hx1, hy1, hx2, hy2 = hr
            h_h = hy2 - hy1
            if not (hx1 - tol <= v_cx <= hx2 + tol):
                continue
            if not (vy1 < hy2 and vy2 > hy1):
                continue
            if hy1 - tol < vy2 < hy2 + h_h * width_margin:
                vr[3] = hy2
            if hy1 - h_h * width_margin < vy1 < hy2 + tol:
                vr[1] = hy1


def _clamp_region_rect_to_max_thickness(
    rect: list[float],
    *,
    orientation: str,
    max_thickness: float,
) -> tuple[list[float], float, float, bool]:
    x1, y1, x2, y2 = [float(value) for value in rect]
    if orientation == "horizontal":
        raw_thickness = max(0.0, y2 - y1)
        draw_thickness = min(raw_thickness, max_thickness)
        if raw_thickness <= max_thickness:
            return [x1, y1, x2, y2], raw_thickness, draw_thickness, False
        center_y = (y1 + y2) / 2.0
        half = draw_thickness / 2.0
        return [x1, center_y - half, x2, center_y + half], raw_thickness, draw_thickness, True

    raw_thickness = max(0.0, x2 - x1)
    draw_thickness = min(raw_thickness, max_thickness)
    if raw_thickness <= max_thickness:
        return [x1, y1, x2, y2], raw_thickness, draw_thickness, False
    center_x = (x1 + x2) / 2.0
    half = draw_thickness / 2.0
    return [center_x - half, y1, center_x + half, y2], raw_thickness, draw_thickness, True


def _mitunet_region_entry(
    region_id: str,
    orientation: str,
    rect: list[float],
    *,
    max_thickness: float,
) -> dict[str, Any]:
    x1, y1, x2, y2 = rect
    clamped_rect, raw_thickness, draw_thickness, was_clamped = _clamp_region_rect_to_max_thickness(
        rect,
        orientation=orientation,
        max_thickness=max_thickness,
    )
    cx1, cy1, cx2, cy2 = clamped_rect
    return {
        "id": region_id,
        "kind": "wall_region",
        "source": "mitunet_mask",
        "orientation": orientation,
        "raw_thickness": float(raw_thickness),
        "draw_thickness": float(draw_thickness),
        "thickness_clamped": bool(was_clamped),
        "raw_bounds": {
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
        },
        "bounds": {
            "x1": float(cx1),
            "y1": float(cy1),
            "x2": float(cx2),
            "y2": float(cy2),
        },
    }


def build_mitunet_region_plan(
    infer_result: dict[str, Any],
    *,
    annotations: list[dict] | None = None,
) -> dict[str, Any]:
    wall_mask = infer_result["_wall_mask"]
    h, w = infer_result["_image_shape"]
    image_shape = (h, w)
    raw_mask_debug = _summarize_binary_mask(wall_mask)

    cleaned = _prepare_mitunet_wall_mask_for_regions(
        wall_mask,
        image_shape=image_shape,
        annotations=annotations,
    )
    cleaned_mask_debug = _summarize_binary_mask(cleaned)
    transform = _resolve_mitunet_plan_transform(image_shape)
    h_rects, v_rects, extraction_meta = _collect_mitunet_region_rectangles(
        cleaned,
        image_shape=image_shape,
        transform=transform,
    )
    h_rects_before_trim = [list(rect) for rect in h_rects]
    v_rects_before_trim = [list(rect) for rect in v_rects]
    _trim_mitunet_region_rectangles(h_rects, v_rects)
    max_wall_thickness = float(MAX_MITUNET_REGION_WALL_THICKNESS)

    regions = [
        *[
            _mitunet_region_entry(
                f"h-region-{index:04d}",
                "horizontal",
                rect,
                max_thickness=max_wall_thickness,
            )
            for index, rect in enumerate(h_rects, start=1)
        ],
        *[
            _mitunet_region_entry(
                f"v-region-{index:04d}",
                "vertical",
                rect,
                max_thickness=max_wall_thickness,
            )
            for index, rect in enumerate(v_rects, start=1)
        ],
    ]
    clamped_region_count = sum(1 for region in regions if region.get("thickness_clamped"))
    horizontal_adjusted_count = sum(
        1
        for before, after in zip(h_rects_before_trim, h_rects)
        if any(abs(float(before[index]) - float(after[index])) > 1e-6 for index in range(4))
    )
    vertical_adjusted_count = sum(
        1
        for before, after in zip(v_rects_before_trim, v_rects)
        if any(abs(float(before[index]) - float(after[index])) > 1e-6 for index in range(4))
    )
    debug = {
        "stage_order": [
            "raw_wall_mask",
            "cleaned_wall_mask",
            "horizontal_extraction",
            "vertical_extraction",
            "trimmed_rectangles",
            "clamped_regions",
        ],
        "input": {
            "image_shape": {"height": int(h), "width": int(w)},
            "annotation_count": len(annotations or []),
            "eraser_count": sum(1 for ann in (annotations or []) if ann.get("type") == "eraser"),
        },
        "raw_wall_mask": raw_mask_debug,
        "cleaned_wall_mask": cleaned_mask_debug,
        "horizontal_extraction": {
            "mask": extraction_meta["horizontal_mask"],
            "candidate_count": extraction_meta["horizontal_candidate_count"],
            "accepted_count": extraction_meta["horizontal_accepted_count"],
            "components": extraction_meta["horizontal_components"],
            "rectangles": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-raw-{index:04d}")
                for index, rect in enumerate(h_rects_before_trim, start=1)
            ],
        },
        "vertical_extraction": {
            "mask": extraction_meta["vertical_mask"],
            "candidate_count": extraction_meta["vertical_candidate_count"],
            "accepted_count": extraction_meta["vertical_accepted_count"],
            "components": extraction_meta["vertical_components"],
            "rectangles": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-raw-{index:04d}")
                for index, rect in enumerate(v_rects_before_trim, start=1)
            ],
        },
        "trimmed_rectangles": {
            "horizontal_adjusted_count": horizontal_adjusted_count,
            "vertical_adjusted_count": vertical_adjusted_count,
            "horizontal_before": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-before-{index:04d}")
                for index, rect in enumerate(h_rects_before_trim, start=1)
            ],
            "horizontal_after": [
                _rect_stage_entry(rect, orientation="horizontal", rect_id=f"h-after-{index:04d}")
                for index, rect in enumerate(h_rects, start=1)
            ],
            "vertical_before": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-before-{index:04d}")
                for index, rect in enumerate(v_rects_before_trim, start=1)
            ],
            "vertical_after": [
                _rect_stage_entry(rect, orientation="vertical", rect_id=f"v-after-{index:04d}")
                for index, rect in enumerate(v_rects, start=1)
            ],
        },
        "clamped_regions": {
            "region_count": len(regions),
            "clamped_region_count": clamped_region_count,
            "clamped_region_ids": [region["id"] for region in regions if region.get("thickness_clamped")],
            "regions": [
                {
                    "id": region["id"],
                    "orientation": region["orientation"],
                    "raw_bounds": region["raw_bounds"],
                    "bounds": region["bounds"],
                    "raw_thickness": region["raw_thickness"],
                    "draw_thickness": region["draw_thickness"],
                    "thickness_clamped": region["thickness_clamped"],
                }
                for region in regions
            ],
        },
    }

    return {
        "mode": MITUNET_MASK_REGIONS_DXF_MODE,
        "meta": {
            "backend": MITUNET_BACKEND,
            "image_shape": {"height": int(h), "width": int(w)},
            "transform": transform,
            "template_used": _TEMPLATE_PATH.exists(),
            "template_path": str(_TEMPLATE_PATH),
            "annotation_count": len(annotations or []),
            "region_count": len(regions),
            "clamped_region_count": clamped_region_count,
            "max_wall_thickness": max_wall_thickness,
            "min_len": extraction_meta["min_len"],
            "wall_thin": extraction_meta["wall_thin"],
            "provenance": build_mitunet_provenance(),
            "_wall_mask": wall_mask,  # kept in-memory for scale calibration flood fill
        },
        "regions": regions,
        "debug": debug,
    }


def _load_mitunet_template_doc():
    import ezdxf

    if _TEMPLATE_PATH.exists():
        return ezdxf.readfile(str(_TEMPLATE_PATH))
    return ezdxf.new("R2010")


def _draw_mitunet_annotations_from_region_plan(
    msp: Any,
    doc: Any,
    annotations: list[dict] | None,
    *,
    image_shape: tuple[int, int],
    transform: dict[str, float],
    wall_thickness: float = 4.0,
) -> int:
    if not annotations:
        return 0

    if "DOORS" not in doc.layers:
        doc.layers.add("DOORS", color=157)
    if "WINS" not in doc.layers:
        doc.layers.add("WINS", color=121)

    rect_count = 0

    for ann in annotations:
        ann_type = ann.get("type", "wall")
        if ann_type == "eraser":
            continue

        dx1, dy1 = _mitunet_region_img_to_dxf(int(ann["x1"]), int(ann["y1"]), image_shape=image_shape, transform=transform)
        dx2, dy2 = _mitunet_region_img_to_dxf(int(ann["x2"]), int(ann["y2"]), image_shape=image_shape, transform=transform)

        if ann_type == "wall":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            thickness = wall_thickness  # match model wall thickness (median)
            if adx >= ady:
                y_mid = (dy1 + dy2) / 2
                x_lo, x_hi = min(dx1, dx2), max(dx1, dx2)
                pts = [
                    (x_lo, y_mid - thickness / 2),
                    (x_hi, y_mid - thickness / 2),
                    (x_hi, y_mid + thickness / 2),
                    (x_lo, y_mid + thickness / 2),
                    (x_lo, y_mid - thickness / 2),
                ]
            else:
                x_mid = (dx1 + dx2) / 2
                y_lo, y_hi = min(dy1, dy2), max(dy1, dy2)
                pts = [
                    (x_mid - thickness / 2, y_lo),
                    (x_mid + thickness / 2, y_lo),
                    (x_mid + thickness / 2, y_hi),
                    (x_mid - thickness / 2, y_hi),
                    (x_mid - thickness / 2, y_lo),
                ]
            poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7})
            poly.close()
            hatch = msp.add_hatch(color=7, dxfattribs={"layer": "WALLS"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            rect_count += 1
            continue

        if ann_type == "door":
            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            door_width = adx if adx >= ady else ady

            if door_width < 2:
                continue

            swing = ann.get("swing")
            if not swing:
                continue  # No swing = skip (user must set direction first)

            dxf_swing = swing

            # First point = hinge. Determine if hinge is mirrored
            # (on the right/top end instead of the normal left/bottom).
            hx, hy = dx1, dy1
            is_horiz = adx >= ady
            mirrored = (dx1 > dx2) if is_horiz else (dy1 > dy2)

            DS = 1.5
            attribs = {"layer": "DOORS", "color": 157}

            if dxf_swing == "up":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx, hy + door_width), dxfattribs=attribs)
                msp.add_line((hx + ds_sign * DS, hy), (hx + ds_sign * DS, hy + door_width), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=attribs)
            elif dxf_swing == "down":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx, hy - door_width), dxfattribs=attribs)
                msp.add_line((hx + ds_sign * DS, hy), (hx + ds_sign * DS, hy - door_width), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=attribs)
            elif dxf_swing == "right":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx + door_width, hy), dxfattribs=attribs)
                msp.add_line((hx, hy + ds_sign * DS), (hx + door_width, hy + ds_sign * DS), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=attribs)
            elif dxf_swing == "left":
                ds_sign = -1 if mirrored else 1
                msp.add_line((hx, hy), (hx - door_width, hy), dxfattribs=attribs)
                msp.add_line((hx, hy + ds_sign * DS), (hx - door_width, hy + ds_sign * DS), dxfattribs=attribs)
                if mirrored:
                    msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=attribs)
                else:
                    msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=attribs)
            continue

        if ann_type == "window":
            from .components.windows import draw_window_h, draw_window_v  # noqa: E402

            exterior = ann.get("swing")  # reuse swing field for exterior side
            if not exterior:
                continue  # No side set = skip (user must pick exterior direction)

            adx = abs(dx2 - dx1)
            ady = abs(dy2 - dy1)
            # Map user direction to draw_window side parameter
            if adx >= ady:
                # Horizontal window: DXF Y-flip means up→bottom, down→top
                side = "bottom" if exterior == "up" else "top"
                x_lo = min(dx1, dx2)
                y_mid = (dy1 + dy2) / 2
                draw_window_h(msp, x_lo, y_mid, adx, side=side)
            else:
                # Vertical window: left→left, right→right
                side = exterior  # already "left" or "right"
                x_mid = (dx1 + dx2) / 2
                y_lo = min(dy1, dy2)
                draw_window_v(msp, x_mid, y_lo, ady, side=side)

    return rect_count


def generate_mitunet_region_dxf(
    region_plan: dict[str, Any],
    out_path: str,
    *,
    annotations: list[dict] | None = None,
    skip_regions: bool = False,
    total_area_sqft: float | None = None,
) -> tuple[int, dict | None]:
    doc = _load_mitunet_template_doc()
    msp = doc.modelspace()

    if "WALLS" not in doc.layers:
        doc.layers.add("WALLS", color=7)

    rect_count = 0
    region_thicknesses: list[float] = []

    if not skip_regions:
        for region in region_plan.get("regions", []):
            bounds = region.get("bounds") or {}
            x1 = float(bounds.get("x1", 0.0))
            y1 = float(bounds.get("y1", 0.0))
            x2 = float(bounds.get("x2", 0.0))
            y2 = float(bounds.get("y2", 0.0))
            if abs(x2 - x1) < 1 or abs(y2 - y1) < 1:
                continue
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
            poly = msp.add_lwpolyline(pts, dxfattribs={"layer": "WALLS", "color": 7})
            poly.close()
            hatch = msp.add_hatch(color=7, dxfattribs={"layer": "WALLS"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            rect_count += 1
            dt = float(region.get("draw_thickness", 0.0))
            if dt > 0:
                region_thicknesses.append(dt)

    # Use median thickness of model regions so annotations match
    if region_thicknesses:
        region_thicknesses.sort()
        mid = len(region_thicknesses) // 2
        median_thickness = region_thicknesses[mid] if len(region_thicknesses) % 2 else (region_thicknesses[mid - 1] + region_thicknesses[mid]) / 2
    else:
        median_thickness = 4.0  # fallback

    meta = region_plan.get("meta", {})
    image_shape_meta = meta.get("image_shape", {})
    image_shape = (
        int(image_shape_meta.get("height", 0)),
        int(image_shape_meta.get("width", 0)),
    )
    rect_count += _draw_mitunet_annotations_from_region_plan(
        msp,
        doc,
        annotations,
        image_shape=image_shape,
        transform=meta.get("transform", {}),
        wall_thickness=median_thickness,
    )

    # --- Dimensions + room labels from label annotations ---
    dims_result = None
    if annotations:
        wall_mask = region_plan.get("meta", {}).get("_wall_mask")
        transform = meta.get("transform", {})
        img_h = image_shape[0]

        dims_result = _add_dims_and_labels(
            doc,
            msp,
            annotations,
            wall_mask,
            image_shape,
            transform,
            img_h,
            total_area_sqft=total_area_sqft,
        )

    doc.saveas(out_path)
    return rect_count, dims_result


def _add_dims_and_labels(doc, msp, annotations, wall_mask, image_shape, transform, img_h, *, total_area_sqft: float | None = None) -> dict | None:
    """Generate simplified exterior dimensions + manual room labels.

    Returns dict with 'computed_rooms' and 'region_overlay' when available.
    """
    try:
        from .scale_calibrator import calibrate_scale, generate_region_overlay, encode_overlay_png
        from .components.dimensions import generate_all_dimensions
        from .observability import log_event

        has_labels = any(a.get("type") == "label" for a in annotations)
        if not has_labels:
            log_event("dims_pipeline_skipped", reason="no_labels")
            return None

        has_sqft = any(a.get("type") == "label" and a.get("sqft") for a in annotations)
        has_total_area = total_area_sqft is not None and float(total_area_sqft) > 0
        render_dimensions = bool((has_total_area or has_sqft) and wall_mask is not None)
        scale_ipp = 1.0
        measurement_context = None
        if render_dimensions:
            measurement_context = calibrate_scale(
                annotations,
                wall_mask,
                image_shape,
                total_area_sqft=float(total_area_sqft) if has_total_area else None,
            )
            if measurement_context is None:
                scale_ipp = 1.0
                render_dimensions = False
            else:
                scale_ipp = float(measurement_context["scale_ipp"])
        log_event(
            "dims_pipeline_start",
            label_count=sum(1 for a in annotations if a.get("type") == "label"),
            has_sqft=has_sqft,
            has_total_area=has_total_area,
            total_area_sqft=round(float(total_area_sqft), 4) if has_total_area else None,
            wall_mask_present=wall_mask is not None,
            render_dimensions=render_dimensions,
            scale_ipp=round(scale_ipp, 6),
            calibration_mode=measurement_context["calibration_mode"] if measurement_context else None,
        )

        counts = generate_all_dimensions(
            doc, msp, annotations,
            scale_ipp=scale_ipp,
            image_shape=image_shape,
            transform=transform,
            wall_mask=wall_mask,
            render_dimensions=render_dimensions,
            measurement_context=measurement_context,
        )
        total = sum(counts.values())
        log_event("dims_pipeline_done", total=total, counts=counts)
        print(f"[DIMS] Generated {total} elements: {counts}", flush=True)

        # Extract computed rooms + region overlay for the API response
        result: dict = {}
        if measurement_context and "room_analysis" in measurement_context:
            room_analysis = measurement_context["room_analysis"]
            rooms = room_analysis.get("rooms", [])
            computed = []
            for room in rooms:
                if room.get("computed_sqft") is not None:
                    label = room.get("label", {})
                    computed.append({
                        "roomName": str(room.get("room_name") or label.get("roomName", "ROOM")).upper(),
                        "sqft": round(float(room["computed_sqft"])),
                        "x1": float(label.get("x1", 0)),
                        "y1": float(label.get("y1", 0)),
                    })
            if computed:
                result["computed_rooms"] = computed

            # Generate colored region overlay
            overlay = generate_region_overlay(room_analysis, image_shape)
            overlay_b64 = encode_overlay_png(overlay)
            if overlay_b64:
                result["region_overlay"] = overlay_b64

        return result if result else None

    except Exception:
        import traceback
        traceback.print_exc()
        return None
