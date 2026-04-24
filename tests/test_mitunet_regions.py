import cv2
import numpy as np

from backend.mitunet_inference import build_mitunet_region_plan
from tests.helpers import build_manual_structure


def _build_short_branch_infer_result() -> dict:
    structure = build_manual_structure(source="mitunet_local", with_openings=False)
    h, w = 400, 400
    wall_mask = np.zeros((h, w), dtype=np.uint8)

    cv2.rectangle(wall_mask, (40, 40), (260, 44), 255, -1)
    cv2.rectangle(wall_mask, (40, 40), (44, 260), 255, -1)
    cv2.rectangle(wall_mask, (44, 150), (48, 154), 255, -1)

    structure["source"] = "mitunet_local"
    structure["_wall_mask"] = wall_mask
    structure["_image_shape"] = (h, w)
    return structure


def test_build_mitunet_region_plan_preserves_short_l_branch():
    infer_result = _build_short_branch_infer_result()

    region_plan = build_mitunet_region_plan(infer_result)

    short_regions = [region for region in region_plan["regions"] if region.get("source_stage") == "short_branch"]

    assert region_plan["debug"]["stage_order"] == [
        "raw_wall_mask",
        "cleaned_wall_mask",
        "horizontal_extraction",
        "vertical_extraction",
        "short_branch_extraction",
        "trimmed_rectangles",
        "clamped_regions",
    ]
    assert region_plan["meta"]["branch_min_len"] >= 4
    assert region_plan["debug"]["short_branch_extraction"]["horizontal_accepted_count"] >= 1
    assert len(short_regions) >= 1
    assert any(region["orientation"] == "horizontal" for region in short_regions)
