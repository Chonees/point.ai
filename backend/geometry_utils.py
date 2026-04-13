"""
geometry_utils.py — Shared geometry primitives for wall junctions.

Used by structure_postprocess, mitunet/annotations, and diagonal_walls.
No ezdxf dependency — pure math.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIAGONAL_ANGLE_THRESHOLD_DEG = 15.0


def is_diagonal(dx: float, dy: float) -> bool:
    """True when a wall segment is significantly off-axis (>15° from both H and V)."""
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return False
    angle_from_h = abs(math.atan2(abs(dy), abs(dx)))
    angle_from_v = abs(math.pi / 2 - angle_from_h)
    threshold = math.radians(DIAGONAL_ANGLE_THRESHOLD_DEG)
    return angle_from_h > threshold and angle_from_v > threshold


# ---------------------------------------------------------------------------
# Line intersection
# ---------------------------------------------------------------------------

def line_intersection(
    p1x: float, p1y: float, d1x: float, d1y: float,
    p2x: float, p2y: float, d2x: float, d2y: float,
) -> tuple[float, float] | None:
    """Intersect line (p1 + t*d1) with (p2 + s*d2).  Returns (x, y) or None."""
    cross = d1x * d2y - d1y * d2x
    if abs(cross) < 1e-8:
        return None
    t = ((p2x - p1x) * d2y - (p2y - p1y) * d2x) / cross
    return (p1x + t * d1x, p1y + t * d1y)


# ---------------------------------------------------------------------------
# Endpoint snapping (Union-Find)
# ---------------------------------------------------------------------------

class UnionFind:
    """Minimal union-find with path compression."""

    __slots__ = ("parent",)

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def snap_endpoint_clusters(
    wall_coords: list[tuple[float, float, float, float]],
    tolerance: float = 12.0,
) -> list[tuple[float, float, float, float]]:
    """Snap wall endpoints that are within *tolerance* to their cluster average.

    Returns a NEW list of wall coordinates with snapped endpoints.
    Walls whose own endpoints are close are never merged with each other.
    """
    if not wall_coords:
        return list(wall_coords)

    # Flatten endpoints
    pts: list[list[float]] = []
    owners: list[tuple[int, int]] = []  # (wall_idx, 0=start | 1=end)
    for wi, (wx1, wy1, wx2, wy2) in enumerate(wall_coords):
        pts.append([wx1, wy1])
        owners.append((wi, 0))
        pts.append([wx2, wy2])
        owners.append((wi, 1))

    # Cluster nearby points (skip same-wall pairs)
    uf = UnionFind(len(pts))
    tol_sq = tolerance * tolerance
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if owners[i][0] == owners[j][0]:
                continue
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            if dx * dx + dy * dy <= tol_sq:
                uf.union(i, j)

    # Compute averages per cluster
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(pts)):
        clusters[uf.find(i)].append(i)

    snapped = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        avg_x = sum(pts[m][0] for m in members) / len(members)
        avg_y = sum(pts[m][1] for m in members) / len(members)
        for m in members:
            pts[m][0] = avg_x
            pts[m][1] = avg_y
        snapped += len(members)

    if snapped == 0:
        return list(wall_coords)

    # Rebuild coordinate list
    out = list(wall_coords)
    for pi, (wi, ep) in enumerate(owners):
        wx1, wy1, wx2, wy2 = out[wi]
        if ep == 0:
            out[wi] = (pts[pi][0], pts[pi][1], wx2, wy2)
        else:
            out[wi] = (wx1, wy1, pts[pi][0], pts[pi][1])

    print(f"[DXF-Snap] Snapped {snapped} wall endpoints into clusters", flush=True)
    return out
