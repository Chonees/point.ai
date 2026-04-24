from pathlib import Path
import base64

import ezdxf
import numpy as np
import pytest

from backend.dxf_preview import build_dxf_preview
from backend.mitunet_inference import build_mitunet_region_plan, regions_to_wall_annotations
from backend.mitunet.dxf_writer import generate_mitunet_region_dxf
from tests.helpers import build_mitunet_infer_result


def _minimal_region_plan() -> dict:
    return {
        "regions": [],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        },
    }


def _workspace_tmp_file(name: str) -> Path:
    root = Path(".test_artifacts")
    root.mkdir(exist_ok=True)
    path = root / name
    if path.exists():
        path.unlink()
    return path


def _polyline_xy_bounds(entity) -> tuple[float, float, float, float]:
    points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def test_generate_mitunet_region_dxf_writes_single_stroke_wall_centerlines_without_legacy_artifacts():
    out_path = _workspace_tmp_file("single_stroke.dxf")
    region_plan = _minimal_region_plan()
    annotations = [
        {
            "id": "wall-1",
            "type": "wall",
            "x1": 10,
            "y1": 40,
            "x2": 90,
            "y2": 40,
            "thickness": 4,
        }
    ]

    rect_count, dims_result = generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    assert rect_count == 1
    assert dims_result is None

    doc = ezdxf.readfile(str(out_path))
    msp = doc.modelspace()

    wall_polys = list(msp.query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    assert wall_polys[0].closed is False
    assert float(getattr(wall_polys[0].dxf, "const_width", 0.0) or 0.0) == 4.0
    x_min, y_min, x_max, y_max = _polyline_xy_bounds(wall_polys[0])
    assert round(x_max - x_min, 3) == 80.0
    assert round(y_max - y_min, 3) == 0.0

    assert len(list(msp.query("HATCH"))) == 0
    assert len(list(msp.query("TEXT"))) == 0
    assert len(list(msp.query("MTEXT"))) == 0
    assert len(list(msp.query("DIMENSION"))) == 0


def test_generate_mitunet_region_dxf_uses_detected_wall_width_for_single_stroke_walls_when_polygon_is_available():
    out_path = _workspace_tmp_file("single_stroke_detected_width.dxf")
    region_plan = {
        "regions": [],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 1.5, "offset_x": 0.0, "offset_y": 0.0},
        },
    }
    annotations = [
        {
            "id": "wall-1",
            "type": "wall",
            "x1": 10,
            "y1": 40,
            "x2": 90,
            "y2": 40,
            "thickness": 4,
            "polygon": [
                {"x": 10, "y": 35},
                {"x": 90, "y": 35},
                {"x": 90, "y": 45},
                {"x": 10, "y": 45},
            ],
        }
    ]

    generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    doc = ezdxf.readfile(str(out_path))
    msp = doc.modelspace()
    wall_polys = list(msp.query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    assert wall_polys[0].closed is False
    assert float(getattr(wall_polys[0].dxf, "const_width", 0.0) or 0.0) == 15.0


def test_generate_mitunet_region_dxf_preserves_small_detected_wall_widths():
    out_path = _workspace_tmp_file("single_stroke_small_detected_width.dxf")
    region_plan = {
        "regions": [],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 1.5, "offset_x": 0.0, "offset_y": 0.0},
        },
    }
    annotations = [
        {
            "id": "wall-1",
            "type": "wall",
            "x1": 10,
            "y1": 40,
            "x2": 90,
            "y2": 40,
            "thickness": 4,
            "polygon": [
                {"x": 10, "y": 38},
                {"x": 90, "y": 38},
                {"x": 90, "y": 42},
                {"x": 10, "y": 42},
            ],
        }
    ]

    generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    doc = ezdxf.readfile(str(out_path))
    msp = doc.modelspace()
    wall_polys = list(msp.query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    assert wall_polys[0].closed is False
    assert float(getattr(wall_polys[0].dxf, "const_width", 0.0) or 0.0) == 6.0


def test_generate_mitunet_region_dxf_keeps_short_bridge_wall_when_endpoint_snapping_clusters_neighbors():
    out_path = _workspace_tmp_file("short_bridge_wall_snap_guard.dxf")
    region_plan = _minimal_region_plan()
    annotations = [
        {
            "id": "wall-left",
            "type": "wall",
            "x1": 10.0,
            "y1": 40.0,
            "x2": 10.0,
            "y2": 52.0,
            "thickness": 4,
            "polygon": [
                {"x": 8.0, "y": 40.0},
                {"x": 12.0, "y": 40.0},
                {"x": 12.0, "y": 52.0},
                {"x": 8.0, "y": 52.0},
            ],
        },
        {
            "id": "wall-bridge",
            "type": "wall",
            "x1": 10.0,
            "y1": 46.0,
            "x2": 14.0,
            "y2": 46.0,
            "thickness": 4,
            "polygon": [
                {"x": 10.0, "y": 44.0},
                {"x": 14.0, "y": 44.0},
                {"x": 14.0, "y": 48.0},
                {"x": 10.0, "y": 48.0},
            ],
        },
        {
            "id": "wall-right",
            "type": "wall",
            "x1": 14.0,
            "y1": 40.0,
            "x2": 14.0,
            "y2": 52.0,
            "thickness": 4,
            "polygon": [
                {"x": 12.0, "y": 40.0},
                {"x": 16.0, "y": 40.0},
                {"x": 16.0, "y": 52.0},
                {"x": 12.0, "y": 52.0},
            ],
        },
    ]

    generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    doc = ezdxf.readfile(str(out_path))
    wall_polys = list(doc.modelspace().query('LWPOLYLINE[layer=="WALLS"]'))

    assert len(wall_polys) == 3
    spans = []
    for poly in wall_polys:
        x_min, y_min, x_max, y_max = _polyline_xy_bounds(poly)
        spans.append(
            (
                round(x_max - x_min, 3),
                round(y_max - y_min, 3),
                round(float(getattr(poly.dxf, "const_width", 0.0) or 0.0), 3),
                bool(poly.closed),
            )
        )
    assert (4.0, 0.0, 4.0, False) in spans
    assert spans.count((0.0, 12.0, 4.0, False)) == 2


def test_build_dxf_preview_renders_closed_wall_strip():
    doc = ezdxf.new("R2010")
    if "WALLS" not in doc.layers:
        doc.layers.add("WALLS", color=7)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(10, 16), (90, 16), (90, 24), (10, 24)],
        close=True,
        dxfattribs={"layer": "WALLS"},
    )

    out_path = _workspace_tmp_file("preview_width.dxf")
    doc.saveas(str(out_path))

    image = np.full((120, 120, 3), 255, dtype=np.uint8)
    import cv2

    ok, encoded = cv2.imencode(".png", image)
    assert ok
    preview = build_dxf_preview(
        str(out_path),
        image_b64=base64.b64encode(encoded.tobytes()).decode("ascii"),
    )

    assert preview is not None

    non_white = np.where(np.any(preview != 255, axis=2))
    assert non_white[0].size > 0
    y_span = int(non_white[0].max()) - int(non_white[0].min()) + 1
    assert y_span >= 5


def test_build_dxf_preview_keeps_mask_native_walls_that_extend_beyond_region_bounds():
    infer_result = build_mitunet_infer_result()
    region_plan = build_mitunet_region_plan(infer_result)
    annotations = regions_to_wall_annotations(region_plan)
    out_path = _workspace_tmp_file("preview_mask_native_bounds.dxf")

    generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    image = np.full((160, 220, 3), 255, dtype=np.uint8)
    import cv2

    ok, encoded = cv2.imencode(".png", image)
    assert ok
    preview = build_dxf_preview(
        str(out_path),
        image_b64=base64.b64encode(encoded.tobytes()).decode("ascii"),
        region_plan=region_plan,
        include_openings=False,
    )

    assert preview is not None
    top_wall_pixel = preview[25, 70]
    lower_wall_pixel = preview[65, 70]
    assert int(top_wall_pixel[2]) > 150 and int(top_wall_pixel[0]) < 80 and int(top_wall_pixel[1]) < 80
    assert int(lower_wall_pixel[2]) > 150 and int(lower_wall_pixel[0]) < 80 and int(lower_wall_pixel[1]) < 80


def test_generate_mitunet_region_dxf_preserves_original_span_for_short_wall_when_resolver_overtrims(monkeypatch: pytest.MonkeyPatch):
    out_path = _workspace_tmp_file("short_wall_preserve_span.dxf")
    region_plan = _minimal_region_plan()
    annotations = [
        {
            "id": "wall-short",
            "type": "wall",
            "x1": 10,
            "y1": 40,
            "x2": 26,
            "y2": 40,
            "thickness": 4,
            "polygon": [
                {"x": 10, "y": 38},
                {"x": 26, "y": 38},
                {"x": 26, "y": 42},
                {"x": 10, "y": 42},
            ],
        }
    ]

    def _overtrimmed(_walls, mode="dxf"):
        assert mode == "dxf"
        return [
            {
                "orientation": "horizontal",
                "mid": 80.0,
                "span_lo": 14.0,
                "span_hi": 22.0,
                "half_lw": 2.0,
            }
        ]

    monkeypatch.setattr("backend.mitunet.annotations.resolve_wall_junctions", _overtrimmed)

    generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    doc = ezdxf.readfile(str(out_path))
    msp = doc.modelspace()
    wall_polys = list(msp.query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    x_min, _, x_max, _ = _polyline_xy_bounds(wall_polys[0])
    assert round(x_max - x_min, 3) == 16.0


def test_generate_mitunet_region_dxf_preserves_subpixel_wall_span_before_img_to_dxf_conversion():
    out_path = _workspace_tmp_file("subpixel_wall_span.dxf")
    region_plan = {
        "regions": [],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 10.0, "offset_x": 0.0, "offset_y": 0.0},
        },
    }
    annotations = [
        {
            "id": "wall-subpixel",
            "type": "wall",
            "x1": 10.2,
            "y1": 40.4,
            "x2": 10.8,
            "y2": 40.4,
            "thickness": 4,
        }
    ]

    rect_count, _ = generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
        annotations=annotations,
        skip_regions=True,
    )

    assert rect_count == 1

    doc = ezdxf.readfile(str(out_path))
    wall_polys = list(doc.modelspace().query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    x_min, _, x_max, _ = _polyline_xy_bounds(wall_polys[0])
    assert round(x_max - x_min, 3) == 6.0


def test_generate_mitunet_region_dxf_preserves_original_span_for_short_region_when_resolver_inverts(monkeypatch: pytest.MonkeyPatch):
    out_path = _workspace_tmp_file("short_region_preserve_span.dxf")
    region_plan = {
        "regions": [
            {
                "id": "h-region-0001",
                "kind": "wall_region",
                "source": "mitunet_mask",
                "source_stage": "short_branch",
                "orientation": "horizontal",
                "draw_thickness": 4.0,
                "bounds": {
                    "x1": 10.0,
                    "y1": 40.0,
                    "x2": 26.0,
                    "y2": 44.0,
                },
            }
        ],
        "meta": {
            "image_shape": {"height": 120, "width": 120},
            "transform": {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        },
    }

    def _inverted(_walls, mode="dxf"):
        assert mode == "dxf"
        return [
            {
                "orientation": "horizontal",
                "mid": 42.0,
                "span_lo": 18.0,
                "span_hi": 12.0,
                "half_lw": 2.0,
            }
        ]

    monkeypatch.setattr("backend.mitunet.dxf_writer.resolve_wall_junctions", _inverted)

    rect_count, _ = generate_mitunet_region_dxf(
        region_plan,
        str(out_path),
    )

    assert rect_count == 1

    doc = ezdxf.readfile(str(out_path))
    wall_polys = list(doc.modelspace().query('LWPOLYLINE[layer=="WALLS"]'))
    assert len(wall_polys) == 1
    x_min, _, x_max, _ = _polyline_xy_bounds(wall_polys[0])
    assert round(x_max - x_min, 3) == 16.0
