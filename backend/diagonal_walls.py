"""
diagonal_walls.py — Diagonal wall polygon computation with miter joints.

Produces the closed polyline (hatch_pts) for a diagonal wall segment,
with mitered corners where it connects to other walls.
"""
from __future__ import annotations

import math
from typing import Any

from .geometry_utils import line_intersection


def diagonal_wall_hatch_pts(
    dx1: float, dy1: float, dx2: float, dy2: float,
    half_thickness: float,
    neighbours: list[tuple[float, float, float, float, float]],
    *,
    ep_tolerance: float | None = None,
    max_miter_dist: float | None = None,
) -> list[tuple[float, float]] | None:
    """Compute a closed polyline for a diagonal wall with mitered endpoints.

    Parameters
    ----------
    dx1, dy1, dx2, dy2 : DXF-space wall centerline endpoints.
    half_thickness : half the wall thickness (inches).
    neighbours : list of (x1, y1, x2, y2, half_thickness) for every OTHER
                 wall that could share an endpoint with this one.
    ep_tolerance : max distance for two endpoints to be considered shared.
    max_miter_dist : max distance a miter corner can be from the junction.

    Returns
    -------
    5-element list of (x, y) forming a closed polygon, or None if degenerate.
    """
    ht = half_thickness
    wall_dx = dx2 - dx1
    wall_dy = dy2 - dy1
    length = math.sqrt(wall_dx * wall_dx + wall_dy * wall_dy)
    if length < 1:
        return None

    udx = wall_dx / length
    udy = wall_dy / length
    nx = -udy * ht
    ny = udx * ht

    ep_tol = ep_tolerance if ep_tolerance is not None else max(ht * 4, 10.0)
    max_dist = max_miter_dist if max_miter_dist is not None else ht * 4

    # Default corners (blunt perpendicular ends)
    c1a = [dx1 + nx, dy1 + ny]
    c1b = [dx1 - nx, dy1 - ny]
    c2a = [dx2 + nx, dy2 + ny]
    c2b = [dx2 - nx, dy2 - ny]

    # Miter each endpoint against the nearest neighbour
    for ox1, oy1, ox2, oy2, o_ht in neighbours:
        # Endpoint 1 — body goes toward P2
        for opx, opy in [(ox1, oy1), (ox2, oy2)]:
            if abs(dx1 - opx) < ep_tol and abs(dy1 - opy) < ep_tol:
                _miter_endpoint(
                    dx1, dy1, (udx, udy), c1a, c1b,
                    (ox1, oy1, ox2, oy2), o_ht, ep_tol, max_dist,
                )
                break

        # Endpoint 2 — body goes toward P1 (reversed direction)
        for opx, opy in [(ox1, oy1), (ox2, oy2)]:
            if abs(dx2 - opx) < ep_tol and abs(dy2 - opy) < ep_tol:
                _miter_endpoint(
                    dx2, dy2, (-udx, -udy), c2a, c2b,
                    (ox1, oy1, ox2, oy2), o_ht, ep_tol, max_dist,
                )
                break

    return [
        (c1a[0], c1a[1]), (c2a[0], c2a[1]),
        (c2b[0], c2b[1]), (c1b[0], c1b[1]),
        (c1a[0], c1a[1]),
    ]


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _miter_endpoint(
    ep_x: float, ep_y: float,
    body_dir: tuple[float, float],
    ca: list[float], cb: list[float],
    other_coords: tuple[float, float, float, float],
    other_ht: float,
    ep_tol: float,
    max_dist: float,
) -> bool:
    """Miter one endpoint of a diagonal wall against a connecting wall.

    Tries both edge pairings (+/+ and +/−) and picks the one whose
    intersection points are closest to the junction.  This always selects
    the correct, non-inverted miter regardless of angle.

    *ca* and *cb* are mutated in-place on success.  Returns True if applied.
    """
    ox1, oy1, ox2, oy2 = other_coords
    for spx, spy, fpx, fpy in [(ox1, oy1, ox2, oy2), (ox2, oy2, ox1, oy1)]:
        if abs(ep_x - spx) > ep_tol or abs(ep_y - spy) > ep_tol:
            continue

        odx, ody = fpx - spx, fpy - spy
        ol = math.sqrt(odx * odx + ody * ody)
        if ol < 1:
            continue
        oudx, oudy = odx / ol, ody / ol
        onx, ony = -oudy * other_ht, oudx * other_ht

        oe_plus = (spx + onx, spy + ony)
        oe_minus = (spx - onx, spy - ony)

        best_ca: list[float] | None = None
        best_cb: list[float] | None = None
        best_score = float("inf")

        for oe_a, oe_b in [(oe_plus, oe_minus), (oe_minus, oe_plus)]:
            ia = line_intersection(
                ca[0], ca[1], body_dir[0], body_dir[1],
                oe_a[0], oe_a[1], oudx, oudy,
            )
            ib = line_intersection(
                cb[0], cb[1], body_dir[0], body_dir[1],
                oe_b[0], oe_b[1], oudx, oudy,
            )
            if ia and ib:
                da = math.sqrt((ia[0] - ep_x) ** 2 + (ia[1] - ep_y) ** 2)
                db = math.sqrt((ib[0] - ep_x) ** 2 + (ib[1] - ep_y) ** 2)
                score = da + db
                if da < max_dist and db < max_dist and score < best_score:
                    best_score = score
                    best_ca = [ia[0], ia[1]]
                    best_cb = [ib[0], ib[1]]

        if best_ca and best_cb:
            ca[0], ca[1] = best_ca[0], best_ca[1]
            cb[0], cb[1] = best_cb[0], best_cb[1]
            return True
        break  # matched endpoint, no need to check the other
    return False
