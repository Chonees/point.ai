import copy

from backend.artifacts import build_preview_image
from backend.benchmark import _rescale_structure_to_original_space
from backend.coordinate_space import DXF_COORDINATE_SPACE
from tests.helpers import build_manual_structure, build_synthetic_structure_image


def test_build_preview_image_leaves_wall_gap_and_draws_opening_markers():
    structure = copy.deepcopy(build_manual_structure(with_openings=True))
    for opening in structure["openings"]:
        if opening["id"] == "opening-window":
            opening["side"] = "top"
        if opening["id"] == "opening-door":
            opening["side"] = "left"
            opening["swing"] = "right"

    preview = build_preview_image(structure, image_b64=build_synthetic_structure_image())

    # Red wall overlay should still trace the wall before the opening.
    assert int(preview[20, 120, 2]) > 200

    # The wall opening itself should remain a real gap in the red wall lines.
    assert int(preview[20, 151, 2]) < 180

    # Window marker should be visible inside the opening span.
    window_pixel = preview[24, 151]
    assert int(window_pixel[1]) > 100
    assert int(window_pixel[2]) > 150

    # Door marker should be visible as a snapped green leaf line.
    door_pixel = preview[60, 130]
    assert int(door_pixel[1]) > 140


def test_rescale_structure_to_original_space_scales_auto_annotation_segments():
    structure = {
        "_auto_annotations": [
            {"type": "window", "x1": 20.0, "y1": 40.0, "x2": 60.0, "y2": 40.0},
            {"type": "door", "x1": 80.0, "y1": 30.0, "x2": 80.0, "y2": 90.0},
        ],
        "structure_meta": {"image_size": {"width": 200, "height": 120}},
    }
    normalization = {
        "scale_x": 2.0,
        "scale_y": 4.0,
        "original_size": {"width": 100, "height": 30},
    }

    rescaled = _rescale_structure_to_original_space(structure, normalization)

    window_ann, door_ann = rescaled["_auto_annotations"]
    assert window_ann == {"type": "window", "x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 10.0}
    assert door_ann == {"type": "door", "x1": 40.0, "y1": 7.5, "x2": 40.0, "y2": 22.5}
    assert rescaled["structure_meta"]["image_size"] == {"width": 100, "height": 30}


def test_build_preview_image_projects_dxf_space_walls_back_to_image_space():
    structure = {
        "model": "DXF-space preview fixture",
        "source": "mitunet_local",
        "walls": [
            {
                "id": "wall-top",
                "orientation": "horizontal",
                "polyline": [{"x": 20.0, "y": 140.0}, {"x": 200.0, "y": 140.0}],
                "thickness": 8.0,
                "is_exterior": True,
                "confidence": 0.95,
            },
        ],
        "openings": [],
        "junctions": [],
        "structure_meta": {
            "image_size": {"width": 220, "height": 160},
            "scale_status": "unverified",
            "unit": "pixel",
            "coordinate_space": DXF_COORDINATE_SPACE,
        },
    }

    preview = build_preview_image(structure, image_b64=build_synthetic_structure_image())

    assert int(preview[20, 120, 2]) > 200
    assert int(preview[140, 120, 2]) < 160
