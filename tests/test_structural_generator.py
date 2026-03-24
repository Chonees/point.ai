"""Tests for the structural DXF generator, including garage/sliding doors."""
import tempfile
from pathlib import Path

from backend.structural_generator import _apply_junction_extensions, _opening_geometry, generate


def _structure_with_door_types():
    """Structure with normal, garage, and sliding doors."""
    return {
        "model": "Test Door Types",
        "source": "test",
        "walls": [
            {
                "id": "wall-0001", "orientation": "horizontal",
                "polyline": [{"x": 0, "y": 0}, {"x": 300, "y": 0}],
                "thickness": 4.0, "is_exterior": True,
            },
            {
                "id": "wall-0002", "orientation": "horizontal",
                "polyline": [{"x": 0, "y": 120}, {"x": 300, "y": 120}],
                "thickness": 4.0, "is_exterior": True,
            },
            {
                "id": "wall-0003", "orientation": "vertical",
                "polyline": [{"x": 0, "y": 0}, {"x": 0, "y": 120}],
                "thickness": 4.0, "is_exterior": True,
            },
            {
                "id": "wall-0004", "orientation": "vertical",
                "polyline": [{"x": 300, "y": 0}, {"x": 300, "y": 120}],
                "thickness": 4.0, "is_exterior": True,
            },
        ],
        "openings": [
            {
                "id": "op-0001", "kind": "door", "wall_id": "wall-0001",
                "position": {"x": 50, "y": 0}, "offset": 35, "span": 30,
                "orientation": "horizontal", "side": "bottom", "swing": "up",
                "door_type": "normal",
            },
            {
                "id": "op-0002", "kind": "door", "wall_id": "wall-0001",
                "position": {"x": 150, "y": 0}, "offset": 120, "span": 60,
                "orientation": "horizontal", "side": "bottom",
                "door_type": "garage",
            },
            {
                "id": "op-0003", "kind": "door", "wall_id": "wall-0002",
                "position": {"x": 240, "y": 120}, "offset": 200, "span": 48,
                "orientation": "horizontal", "side": "top",
                "door_type": "sliding",
            },
        ],
        "structure_meta": {"image_size": None, "scale_status": "calibrated", "unit": "inch"},
    }


def test_generate_with_all_door_types_produces_valid_dxf():
    """DXF generation should succeed with normal, garage, and sliding doors."""
    structure = _structure_with_door_types()

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        out_path = f.name

    generate(structure, out_path)

    content = Path(out_path).read_text(encoding="utf-8", errors="ignore")
    assert "WALLS" in content
    assert "DOORS" in content
    assert len(content) > 500


def test_generate_minimal_structure():
    """Minimal structure with just walls produces a valid DXF."""
    structure = {
        "walls": [
            {
                "id": "w1", "orientation": "horizontal",
                "polyline": [{"x": 0, "y": 0}, {"x": 100, "y": 0}],
                "thickness": 4.0, "is_exterior": True,
            },
        ],
        "openings": [],
    }

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        out_path = f.name

    generate(structure, out_path)

    content = Path(out_path).read_text(encoding="utf-8", errors="ignore")
    assert "WALLS" in content


def test_opening_offset_uses_original_wall_start_after_extension():
    wall = {
        "id": "w1",
        "orientation": "horizontal",
        "coord": 20.0,
        "start": 12.0,
        "end": 108.0,
        "base_start": 20.0,
        "base_end": 100.0,
        "thickness": 8.0,
        "draw_thickness": 8.0,
        "is_exterior": True,
    }
    opening = {
        "id": "op-1",
        "kind": "door",
        "wall_id": "w1",
        "offset": 10.0,
        "span": 24.0,
    }

    geometry = _opening_geometry(opening, wall)

    assert geometry["start"] == 30.0
    assert geometry["end"] == 54.0


def test_junction_extensions_use_detected_wall_thickness():
    wall = {
        "id": "w1",
        "orientation": "horizontal",
        "coord": 20.0,
        "start": 20.0,
        "end": 100.0,
        "base_start": 20.0,
        "base_end": 100.0,
        "thickness": 8.0,
        "draw_thickness": 8.0,
        "is_exterior": True,
    }
    wall_map = {"w1": wall}
    junctions = [{"point": {"x": 20.0, "y": 20.0}, "type": "L", "wall_ids": ["w1"]}]

    _apply_junction_extensions([wall], junctions, wall_map)

    assert wall["start"] == 12.0
