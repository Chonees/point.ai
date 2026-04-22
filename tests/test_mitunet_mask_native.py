import cv2
import numpy as np

from backend.mitunet.annotations import (
    _snap_annotations_to_wall_edges,
    align_opening_annotations_to_walls,
    regions_to_wall_annotations,
)
from backend.benchmark import _rasterize_structure_walls_to_shape
from backend.mitunet.mask_native import (
    _collapse_parallel_widening_duplicates,
    _records_coverage_mask,
    build_mask_native_wall_annotations,
)
from backend.mitunet_inference import build_mitunet_region_plan
from tests.helpers import build_mitunet_infer_result


def _diagonal_wall_mask() -> np.ndarray:
    mask = np.zeros((220, 220), dtype=np.uint8)
    cv2.line(mask, (40, 180), (180, 40), 255, 10)
    return mask


def _short_branch_wall_mask() -> np.ndarray:
    mask = np.zeros((220, 220), dtype=np.uint8)
    cv2.rectangle(mask, (40, 40), (180, 48), 255, -1)
    cv2.rectangle(mask, (40, 40), (48, 180), 255, -1)
    cv2.rectangle(mask, (48, 120), (84, 128), 255, -1)
    return mask


def _simple_rect_wall_mask() -> np.ndarray:
    mask = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 40), (120, 60), 255, -1)
    return mask


def _staircase_horizontal_wall_mask() -> np.ndarray:
    mask = np.zeros((90, 140), dtype=np.uint8)
    points = np.array(
        [
            [10, 34],
            [20, 35],
            [30, 34],
            [40, 35],
            [50, 34],
            [60, 35],
            [70, 34],
            [80, 35],
            [90, 34],
            [100, 35],
            [110, 34],
            [120, 35],
            [120, 45],
            [10, 45],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, [points], 255)
    return mask


def _mini_t_wall_mask() -> np.ndarray:
    mask = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 60), (140, 70), 255, -1)
    cv2.rectangle(mask, (76, 28), (86, 70), 255, -1)
    return mask


def _centered_stub_artifact_wall_mask() -> np.ndarray:
    mask = np.zeros((120, 120), dtype=np.uint8)
    cv2.rectangle(mask, (35, 10), (45, 110), 255, -1)
    cv2.rectangle(mask, (30, 58), (50, 62), 255, -1)
    return mask


def _thin_endpoint_cap_wall_mask() -> np.ndarray:
    mask = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 60), (140, 70), 255, -1)
    cv2.rectangle(mask, (20, 56), (30, 60), 255, -1)
    return mask


def _thin_mini_t_cap_wall_mask() -> np.ndarray:
    mask = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 60), (140, 70), 255, -1)
    cv2.rectangle(mask, (78, 56), (86, 60), 255, -1)
    return mask


def _horizontal_wall_with_parallel_widening_artifact_mask() -> np.ndarray:
    mask = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 60), (140, 70), 255, -1)
    cv2.rectangle(mask, (40, 71), (80, 76), 255, -1)
    return mask


def _load_case_0088_office_bath_mask() -> np.ndarray:
    wall_mask = cv2.imread(
        "tests/fixtures/mask_native_case_0088_office_bath_raw.png",
        cv2.IMREAD_GRAYSCALE,
    )
    assert wall_mask is not None
    return wall_mask


def _load_case_0098_raw_wall_mask() -> np.ndarray:
    wall_mask = cv2.imread(
        "tests/fixtures/mask_native_case_0098_raw.png",
        cv2.IMREAD_GRAYSCALE,
    )
    assert wall_mask is not None
    return wall_mask


def _annotation_signature(annotations: list[dict]) -> list[tuple]:
    normalized: list[tuple] = []
    for annotation in annotations:
        polygon = tuple(
            (round(float(point["x"]), 1), round(float(point["y"]), 1))
            for point in annotation.get("polygon") or []
        )
        normalized.append(
            (
                str(annotation.get("orientation")),
                round(float(annotation["x1"]), 1),
                round(float(annotation["y1"]), 1),
                round(float(annotation["x2"]), 1),
                round(float(annotation["y2"]), 1),
                round(float(annotation.get("_mean_width_px", 0.0)), 3),
                polygon,
            )
        )
    return sorted(normalized)


def _residual_component_areas(
    wall_mask: np.ndarray,
    annotations: list[dict],
) -> list[int]:
    records = [
        {
            "orientation": str(annotation["orientation"]),
            "x1": float(annotation["x1"]),
            "y1": float(annotation["y1"]),
            "x2": float(annotation["x2"]),
            "y2": float(annotation["y2"]),
            "mean_width_px": float(annotation.get("_mean_width_px", 0.0)),
        }
        for annotation in annotations
    ]
    coverage = _records_coverage_mask(records, wall_mask.shape)
    residual = np.logical_and(wall_mask > 0, coverage == 0).astype(np.uint8)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    return sorted(
        [int(stats[label, cv2.CC_STAT_AREA]) for label in range(1, num_labels)],
        reverse=True,
    )


def _annotation_mask_metrics(
    wall_mask: np.ndarray,
    annotations: list[dict],
) -> tuple[float, float, float]:
    records = [
        {
            "orientation": str(annotation["orientation"]),
            "x1": float(annotation["x1"]),
            "y1": float(annotation["y1"]),
            "x2": float(annotation["x2"]),
            "y2": float(annotation["y2"]),
            "mean_width_px": float(annotation.get("_mean_width_px", 0.0)),
        }
        for annotation in annotations
    ]
    coverage = _records_coverage_mask(records, wall_mask.shape) > 0
    target = wall_mask > 0
    intersection = float(np.logical_and(coverage, target).sum())
    predicted = float(coverage.sum())
    expected = float(target.sum())
    union = float(np.logical_or(coverage, target).sum())
    precision = intersection / max(predicted, 1.0)
    recall = intersection / max(expected, 1.0)
    iou = intersection / max(union, 1.0)
    return iou, precision, recall


def test_build_mask_native_wall_annotations_preserves_diagonal_wall():
    annotations = build_mask_native_wall_annotations(_diagonal_wall_mask())

    diagonal = [ann for ann in annotations if ann.get("orientation") == "diagonal"]

    assert len(diagonal) >= 1
    longest = max(
        diagonal,
        key=lambda ann: ((ann["x2"] - ann["x1"]) ** 2 + (ann["y2"] - ann["y1"]) ** 2),
    )
    dx = abs(longest["x2"] - longest["x1"])
    dy = abs(longest["y2"] - longest["y1"])
    assert dx > 80
    assert dy > 80
    assert 0.6 <= (dy / dx) <= 1.4
    assert len(longest.get("polygon") or []) == 4


def test_build_mask_native_wall_annotations_preserves_short_l_branch():
    annotations = build_mask_native_wall_annotations(_short_branch_wall_mask())

    horizontal = [ann for ann in annotations if ann.get("orientation") == "horizontal"]

    assert any(
        min(float(ann["x1"]), float(ann["x2"])) <= 56.0
        and max(float(ann["x1"]), float(ann["x2"])) >= 72.0
        and 118.0 <= float(ann["y1"]) <= 130.0
        for ann in horizontal
    )


def test_build_mask_native_wall_annotations_condenses_staircase_wall_into_single_span():
    annotations = build_mask_native_wall_annotations(_staircase_horizontal_wall_mask())

    horizontal = [ann for ann in annotations if ann.get("orientation") == "horizontal"]

    assert len(horizontal) == 1
    wall = horizontal[0]
    assert min(float(wall["x1"]), float(wall["x2"])) <= 16.0
    assert max(float(wall["x1"]), float(wall["x2"])) >= 116.0
    assert 36.0 <= float(wall["y1"]) <= 44.0


def test_build_mask_native_wall_annotations_preserves_mini_t_branch_after_condensation():
    annotations = build_mask_native_wall_annotations(_mini_t_wall_mask())

    horizontal = [
        ann for ann in annotations
        if ann.get("orientation") == "horizontal"
        and max(float(ann["x1"]), float(ann["x2"])) - min(float(ann["x1"]), float(ann["x2"])) >= 80.0
    ]
    vertical = [
        ann for ann in annotations
        if ann.get("orientation") == "vertical"
        and max(float(ann["y1"]), float(ann["y2"])) - min(float(ann["y1"]), float(ann["y2"])) >= 24.0
    ]

    assert len(horizontal) == 1
    assert len(vertical) == 1
    stem = vertical[0]
    assert 74.0 <= float(stem["x1"]) <= 88.0
    assert min(float(stem["y1"]), float(stem["y2"])) <= 34.0


def test_build_mask_native_wall_annotations_prunes_centered_stub_artifacts():
    annotations = build_mask_native_wall_annotations(_centered_stub_artifact_wall_mask())

    horizontal = [ann for ann in annotations if ann.get("orientation") == "horizontal"]
    vertical = [ann for ann in annotations if ann.get("orientation") == "vertical"]

    assert len(vertical) == 1
    assert len(horizontal) == 0


def test_build_mask_native_wall_annotations_recovers_thin_endpoint_cap_completion():
    annotations = build_mask_native_wall_annotations(_thin_endpoint_cap_wall_mask())

    vertical = [ann for ann in annotations if ann.get("orientation") == "vertical"]

    assert len(vertical) >= 1
    assert any(
        22.0 <= float(ann["x1"]) <= 28.0
        and min(float(ann["y1"]), float(ann["y2"])) <= 57.0
        and max(float(ann["y1"]), float(ann["y2"])) >= 64.0
        for ann in vertical
    )


def test_build_mask_native_wall_annotations_recovers_thin_mini_t_cap():
    annotations = build_mask_native_wall_annotations(_thin_mini_t_cap_wall_mask())

    vertical = [ann for ann in annotations if ann.get("orientation") == "vertical"]

    assert len(vertical) >= 1
    assert any(
        80.0 <= float(ann["x1"]) <= 84.0
        and min(float(ann["y1"]), float(ann["y2"])) <= 57.0
        and max(float(ann["y1"]), float(ann["y2"])) >= 64.0
        for ann in vertical
    )


def test_build_mask_native_wall_annotations_is_deterministic_for_real_case_0088():
    wall_mask = _load_case_0088_office_bath_mask()

    first = _annotation_signature(build_mask_native_wall_annotations(wall_mask))
    second = _annotation_signature(build_mask_native_wall_annotations(wall_mask))
    third = _annotation_signature(build_mask_native_wall_annotations(wall_mask))

    assert second == first
    assert third == first


def test_build_mask_native_wall_annotations_preserves_precise_office_bath_footprint_for_real_case_0088():
    wall_mask = _load_case_0088_office_bath_mask()

    annotations = build_mask_native_wall_annotations(wall_mask)
    _iou, precision, recall = _annotation_mask_metrics(wall_mask, annotations)

    assert precision >= 0.75
    assert recall >= 0.84


def test_build_mask_native_wall_annotations_recovers_real_case_0088_top_right_border_continuation():
    wall_mask = _load_case_0088_office_bath_mask()

    annotations = build_mask_native_wall_annotations(wall_mask)
    vertical = [ann for ann in annotations if ann.get("orientation") == "vertical"]

    assert any(
        258.0 <= float(ann["x1"]) <= 266.5
        and min(float(ann["y1"]), float(ann["y2"])) <= 40.0
        and max(float(ann["y1"]), float(ann["y2"])) >= 70.0
        for ann in vertical
    )


def test_build_mask_native_wall_annotations_keeps_parallel_widening_artifact_inside_support_mask():
    annotations = build_mask_native_wall_annotations(_horizontal_wall_with_parallel_widening_artifact_mask())
    iou, precision, recall = _annotation_mask_metrics(
        _horizontal_wall_with_parallel_widening_artifact_mask(),
        annotations,
    )

    assert iou >= 0.7
    assert precision >= 0.7
    assert recall >= 0.99


def test_build_mask_native_wall_annotations_avoids_real_case_0098_false_positive_overfill():
    wall_mask = _load_case_0098_raw_wall_mask()

    annotations = build_mask_native_wall_annotations(wall_mask)
    iou, precision, recall = _annotation_mask_metrics(wall_mask, annotations)

    assert iou >= 0.7
    assert precision >= 0.72
    assert recall >= 0.95


def test_build_mask_native_wall_annotations_limits_real_case_0098_wall_count_explosion():
    wall_mask = _load_case_0098_raw_wall_mask()

    annotations = build_mask_native_wall_annotations(wall_mask)
    walls = [ann for ann in annotations if ann.get("type") == "wall"]

    assert len(walls) <= 72


def test_collapse_parallel_widening_duplicates_keeps_strongest_nested_span_without_extension():
    support_mask = np.zeros((120, 120), dtype=np.uint8)
    cv2.rectangle(support_mask, (44, 72), (55, 83), 255, -1)
    records = [
        {
            "orientation": "vertical",
            "x1": 49.5,
            "y1": 74.9,
            "x2": 49.5,
            "y2": 81.0,
            "mean_width_px": 11.384,
        },
        {
            "orientation": "vertical",
            "x1": 49.5,
            "y1": 73.8,
            "x2": 49.5,
            "y2": 81.0,
            "mean_width_px": 9.624,
        },
    ]

    collapsed = _collapse_parallel_widening_duplicates(records, support_mask)

    assert len(collapsed) == 1
    kept = collapsed[0]
    assert kept["orientation"] == "vertical"
    assert float(kept["x1"]) == 49.5
    assert float(kept["y1"]) == 74.9
    assert float(kept["y2"]) == 81.0
    assert float(kept["mean_width_px"]) == 11.384


def test_regions_to_wall_annotations_falls_back_to_mask_native_when_regions_are_empty():
    wall_mask = _diagonal_wall_mask()
    infer_result = {
        "source": "mitunet_local",
        "_wall_mask": wall_mask,
        "_image_shape": wall_mask.shape,
    }

    region_plan = build_mitunet_region_plan(infer_result)
    annotations = regions_to_wall_annotations(region_plan)

    assert len(annotations) >= 1
    assert region_plan["meta"]["region_count"] <= 2
    assert any(
        abs(float(ann["x2"]) - float(ann["x1"])) > 80.0
        and abs(float(ann["y2"]) - float(ann["y1"])) > 80.0
        for ann in annotations
    )


def test_align_opening_annotations_to_walls_rewrites_wall_ids_to_mask_native_walls():
    infer_result = build_mitunet_infer_result()
    region_plan = build_mitunet_region_plan(infer_result)
    wall_annotations = regions_to_wall_annotations(region_plan)

    aligned = align_opening_annotations_to_walls(
        wall_annotations,
        [
            {
                "id": "legacy-window",
                "type": "window",
                "x1": 40.0,
                "y1": 24.0,
                "x2": 70.0,
                "y2": 24.0,
                "wall_id": "legacy-top",
            },
            {
                "id": "legacy-door",
                "type": "door",
                "x1": 154.0,
                "y1": 50.0,
                "x2": 154.0,
                "y2": 80.0,
                "wall_id": "legacy-vertical",
            },
        ],
        image_shape=(160, 220),
    )

    wall_ids = {annotation["id"] for annotation in wall_annotations}
    assert len(aligned) == 2
    assert all(annotation["wall_id"] in wall_ids for annotation in aligned)
    window = next(annotation for annotation in aligned if annotation["type"] == "window")
    door = next(annotation for annotation in aligned if annotation["type"] == "door")
    assert window["y1"] == window["y2"] == 25.0
    assert door["x1"] == door["x2"] == 155.0


def test_benchmark_rasterizer_fills_wall_polygon_footprint():
    structure = {
        "walls": [
            {
                "id": "poly-wall",
                "polygon": [
                    {"x": 20.0, "y": 20.0},
                    {"x": 80.0, "y": 20.0},
                    {"x": 80.0, "y": 40.0},
                    {"x": 20.0, "y": 40.0},
                ],
                "polyline": [{"x": 20.0, "y": 30.0}, {"x": 80.0, "y": 30.0}],
                "thickness": 4.0,
            }
        ]
    }

    mask = _rasterize_structure_walls_to_shape(structure, (100, 100))

    assert int(mask.sum()) > 1000


def test_mask_native_polygon_preserves_wall_end_caps_for_simple_rect_wall():
    wall_mask = _simple_rect_wall_mask()
    annotations = build_mask_native_wall_annotations(wall_mask)

    longest = max(
        annotations,
        key=lambda ann: abs(float(ann["x2"]) - float(ann["x1"])) + abs(float(ann["y2"]) - float(ann["y1"])),
    )
    structure = {"walls": [longest]}
    rasterized = _rasterize_structure_walls_to_shape(structure, wall_mask.shape)
    intersection = np.logical_and(rasterized, wall_mask > 0).sum()
    union = np.logical_or(rasterized, wall_mask > 0).sum()
    iou = float(intersection / union)

    assert iou > 0.9


def test_snap_annotations_to_wall_edges_updates_polygon_to_match_snapped_span():
    annotations = [
        {
            "id": "wall-h",
            "type": "wall",
            "x1": 10.0,
            "y1": 50.0,
            "x2": 40.0,
            "y2": 50.0,
            "thickness": 4,
            "orientation": "horizontal",
            "_mean_width_px": 9.0,
            "polygon": [
                {"x": 6.0, "y": 46.0},
                {"x": 44.0, "y": 46.0},
                {"x": 44.0, "y": 54.0},
                {"x": 6.0, "y": 54.0},
            ],
        },
        {
            "id": "wall-v",
            "type": "wall",
            "x1": 40.0,
            "y1": 20.0,
            "x2": 40.0,
            "y2": 50.0,
            "thickness": 4,
            "orientation": "vertical",
            "_mean_width_px": 9.0,
            "polygon": [
                {"x": 36.0, "y": 16.0},
                {"x": 44.0, "y": 16.0},
                {"x": 44.0, "y": 54.0},
                {"x": 36.0, "y": 54.0},
            ],
        },
    ]

    _snap_annotations_to_wall_edges(annotations)

    horizontal = annotations[0]
    polygon_xs = [point["x"] for point in horizontal["polygon"]]
    assert round(max(polygon_xs), 1) >= round(float(horizontal["x2"]), 1)
