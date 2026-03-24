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

import cv2
import numpy as np

MITUNET_BACKEND = "mitunet_local"

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


def generate_mitunet_dxf(infer_result: dict[str, Any], out_path: str,
                         annotations: list[dict] | None = None) -> int:
    """Generate DXF with MARCA REGISTRADA template + wall rectangles with hatch.

    Returns the number of wall rectangles drawn.
    """
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

    # --- Draw all rects ---
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
                thickness = 4  # wall thickness
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

                # Hinge = start point, door end = end point
                hx, hy = dx1, dy1
                ex, ey = dx2, dy2
                door_width = ((ex - hx) ** 2 + (ey - hy) ** 2) ** 0.5
                if door_width < 2:
                    continue

                # Determine if slab is mostly H or V based on user's line
                adx = abs(ex - hx)
                ady = abs(ey - hy)

                if ady >= adx:
                    # Slab is VERTICAL (user drew up or down)
                    # Door goes from hinge to end along Y
                    sy = 1 if ey > hy else -1  # direction along slab
                    # Swing is perpendicular (left or right)
                    sx = 1 if swing == "right" else -1

                    # Slab: 2 parallel vertical lines
                    msp.add_line((hx, hy), (hx, hy + sy * door_width), dxfattribs=DA)
                    msp.add_line((hx + sx * slab, hy), (hx + sx * slab, hy + sy * door_width), dxfattribs=DA)
                    # Arc from hinge, radius = door_width, swings perpendicular
                    if sy > 0 and sx > 0:
                        msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=DA)
                    elif sy > 0 and sx < 0:
                        msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=DA)
                    elif sy < 0 and sx > 0:
                        msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=DA)
                    else:  # sy < 0, sx < 0
                        msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=DA)
                else:
                    # Slab is HORIZONTAL (user drew left or right)
                    sx = 1 if ex > hx else -1  # direction along slab
                    # Swing is perpendicular (up or down)
                    sy = 1 if swing == "up" else -1

                    # Slab: 2 parallel horizontal lines
                    msp.add_line((hx, hy), (hx + sx * door_width, hy), dxfattribs=DA)
                    msp.add_line((hx, hy + sy * slab), (hx + sx * door_width, hy + sy * slab), dxfattribs=DA)
                    # Arc
                    if sx > 0 and sy > 0:
                        msp.add_arc((hx, hy), door_width, 0, 90, dxfattribs=DA)
                    elif sx > 0 and sy < 0:
                        msp.add_arc((hx, hy), door_width, 270, 360, dxfattribs=DA)
                    elif sx < 0 and sy > 0:
                        msp.add_arc((hx, hy), door_width, 90, 180, dxfattribs=DA)
                    else:  # sx < 0, sy < 0
                        msp.add_arc((hx, hy), door_width, 180, 270, dxfattribs=DA)

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
