from __future__ import annotations

import cv2
import numpy as np


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
