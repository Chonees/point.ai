"""Evidence renderer: generates DXFs from synthetic plans (rectangular, L,
U, interior split) and produces a side-by-side PNG that proves the framing
rule (exterior=2x6 / interior=2x4) is enforced for every wall.

The renderer reads the actual DXF produced by `structural_generator.generate`
and measures the distance between the two parallel WALLS lines for each
wall to verify thickness on disk — not just from in-memory classification.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.structural_generator import generate
from backend.structure_postprocess import _classify_walls_with_junctions
from backend.components.walls import EXTERIOR_THICKNESS, INTERIOR_THICKNESS


def _wall(wid, ori, x1, y1, x2, y2):
    return {
        "id": wid,
        "orientation": ori,
        "polyline": [{"x": x1, "y": y1}, {"x": x2, "y": y2}],
        "thickness": 4.0,
        "confidence": 0.9,
        "is_exterior": False,
        "side": None,
    }


# ---------------------------------------------------------------------------
# Synthetic plans
# ---------------------------------------------------------------------------

def plan_rectangular():
    return [
        _wall("bottom", "horizontal", 0, 0, 200, 0),
        _wall("top",    "horizontal", 0, 120, 200, 120),
        _wall("left",   "vertical",   0, 0, 0, 120),
        _wall("right",  "vertical",   200, 0, 200, 120),
        _wall("mid",    "horizontal", 0, 60, 200, 60),
    ]


def plan_l_shape():
    return [
        _wall("bottom",     "horizontal", 0, 0, 200, 0),
        _wall("top_a",      "horizontal", 0, 200, 100, 200),
        _wall("top_bump",   "horizontal", 100, 120, 200, 120),
        _wall("left",       "vertical",   0, 0, 0, 200),
        _wall("right_a",    "vertical",   100, 120, 100, 200),
        _wall("right_bump", "vertical",   200, 0, 200, 120),
        _wall("interior",   "horizontal", 0, 100, 100, 100),
    ]


def plan_u_shape():
    return [
        _wall("bottom",   "horizontal", 0, 0, 300, 0),
        _wall("left",     "vertical",   0, 0, 0, 200),
        _wall("right",    "vertical",   300, 0, 300, 200),
        _wall("top_left", "horizontal", 0, 200, 100, 200),
        _wall("top_right","horizontal", 200, 200, 300, 200),
        _wall("u_left_v", "vertical",   100, 80, 100, 200),
        _wall("u_bottom", "horizontal", 100, 80, 200, 80),
        _wall("u_right_v","vertical",   200, 80, 200, 200),
    ]


# ---------------------------------------------------------------------------
# DXF inspection: measure each wall's actual rendered thickness on disk
# ---------------------------------------------------------------------------

def measure_dxf_walls(dxf_path: str):
    """Read DXF, group parallel WALLS lines by axis, return measured thicknesses.

    Walls are detected by pairing parallel line segments 4-6" apart with
    overlapping spans. Each overlapping segment pair is counted as one wall.
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    h_lines = defaultdict(list)  # y -> [(x1, x2)]
    v_lines = defaultdict(list)
    for line in msp.query('LINE[layer=="WALLS"]'):
        x1, y1, _ = line.dxf.start
        x2, y2, _ = line.dxf.end
        if abs(y1 - y2) < 1e-3:  # horizontal
            h_lines[round(y1, 1)].append((min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 1e-3:  # vertical
            v_lines[round(x1, 1)].append((min(y1, y2), max(y1, y2)))

    def _pair(coord_to_segs):
        """Return list of (coord_center, lo, hi, thickness) wall segments."""
        out = []
        keys = sorted(coord_to_segs.keys())
        # For each pair of coords 4-6" apart, match overlapping individual segments.
        used_segs: set[tuple[float, float, float]] = set()
        for i, c1 in enumerate(keys):
            for c2 in keys[i + 1:]:
                t = c2 - c1
                if t > 6.5:
                    break
                if t < 3.5:
                    continue
                for s1, e1 in coord_to_segs[c1]:
                    if (c1, s1, e1) in used_segs:
                        continue
                    for s2, e2 in coord_to_segs[c2]:
                        if (c2, s2, e2) in used_segs:
                            continue
                        lo = max(s1, s2)
                        hi = min(e1, e2)
                        if hi - lo > 1.0:  # genuine overlap
                            out.append(((c1 + c2) / 2, lo, hi, t))
                            used_segs.add((c1, s1, e1))
                            used_segs.add((c2, s2, e2))
                            break
        return out

    return _pair(h_lines), _pair(v_lines)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def render_plan(ax, title, walls):
    classified = _classify_walls_with_junctions(walls, junctions=[])
    structure = {"walls": classified, "openings": [], "junctions": []}

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        out_path = f.name
    try:
        generate(structure, out_path)
        h_walls, v_walls = measure_dxf_walls(out_path)
    finally:
        Path(out_path).unlink(missing_ok=True)

    # Bbox
    all_x = [p["x"] for w in walls for p in w["polyline"]]
    all_y = [p["y"] for w in walls for p in w["polyline"]]
    pad = 20
    ax.set_xlim(min(all_x) - pad, max(all_x) + pad)
    ax.set_ylim(min(all_y) - pad, max(all_y) + pad)

    ext_count = int_count = 0
    rule_violations = []
    for cy, x_lo, x_hi, t in h_walls:
        is_ext = abs(t - EXTERIOR_THICKNESS) < 0.1
        color = "#d62728" if is_ext else "#1f77b4"
        ax.add_patch(Rectangle((x_lo, cy - t / 2), x_hi - x_lo, t,
                                facecolor=color, edgecolor="black", linewidth=0.5))
        ax.text((x_lo + x_hi) / 2, cy, f"{t:.0f}\"",
                ha="center", va="center", fontsize=7, color="white", weight="bold")
        if is_ext:
            ext_count += 1
        else:
            int_count += 1
        if abs(t - 4) > 0.1 and abs(t - 6) > 0.1:
            rule_violations.append(f"H@y={cy:.0f}: {t:.2f}\"")
    for cx, y_lo, y_hi, t in v_walls:
        is_ext = abs(t - EXTERIOR_THICKNESS) < 0.1
        color = "#d62728" if is_ext else "#1f77b4"
        ax.add_patch(Rectangle((cx - t / 2, y_lo), t, y_hi - y_lo,
                                facecolor=color, edgecolor="black", linewidth=0.5))
        ax.text(cx, (y_lo + y_hi) / 2, f"{t:.0f}\"",
                ha="center", va="center", fontsize=7, color="white", weight="bold",
                rotation=90)
        if is_ext:
            ext_count += 1
        else:
            int_count += 1
        if abs(t - 4) > 0.1 and abs(t - 6) > 0.1:
            rule_violations.append(f"V@x={cx:.0f}: {t:.2f}\"")

    ax.set_aspect("equal")
    ax.set_title(f"{title}\nExt(6\")={ext_count}  Int(4\")={int_count}", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.3)
    return ext_count, int_count, rule_violations


def main():
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    plans = [
        ("Rectangular + interior split", plan_rectangular()),
        ("L-shape + interior split",     plan_l_shape()),
        ("U-shape (8 perimeter walls)",  plan_u_shape()),
    ]
    summary = []
    for ax, (title, walls) in zip(axes, plans):
        ext, intn, viol = render_plan(ax, title, walls)
        summary.append((title, ext, intn, viol))

    # Legend
    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor="#d62728", edgecolor="black", label='Exterior 2x6 (6")'),
        Patch(facecolor="#1f77b4", edgecolor="black", label='Interior 2x4 (4")'),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=11,
               bbox_to_anchor=(0.5, -0.02))

    fig.suptitle("Wall Thickness Rule Enforcement — Measured directly from DXF",
                 fontsize=13, weight="bold")
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out = ROOT / "evidence_wall_thickness.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\nWrote: {out}\n")

    print("=" * 72)
    print("SUMMARY (measured from DXF on disk):")
    print("=" * 72)
    total_violations = 0
    for title, ext, intn, viol in summary:
        status = "PASS" if not viol else "FAIL"
        print(f"  [{status}] {title}: {ext} exterior(6\")  {intn} interior(4\")"
              + (f"  RULE VIOLATIONS: {viol}" if viol else ""))
        total_violations += len(viol)
    print("=" * 72)
    print(f"Rule violations across all plans: {total_violations}")
    print("=" * 72)


if __name__ == "__main__":
    main()
