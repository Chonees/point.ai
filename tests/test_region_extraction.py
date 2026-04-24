import cv2
import numpy as np

from backend.mitunet.region_extraction import _collect_mitunet_region_rectangles


def test_collect_mitunet_region_rectangles_preserves_short_l_branch_components():
    image_shape = (400, 400)
    transform = {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0}
    wall_mask = np.zeros(image_shape, dtype=np.uint8)

    cv2.rectangle(wall_mask, (40, 40), (260, 44), 255, -1)
    cv2.rectangle(wall_mask, (40, 40), (44, 260), 255, -1)
    cv2.rectangle(wall_mask, (44, 150), (48, 154), 255, -1)

    h_rects, v_rects, extraction_meta = _collect_mitunet_region_rectangles(
        wall_mask,
        image_shape=image_shape,
        transform=transform,
    )

    assert extraction_meta["branch_min_len"] >= 4
    assert extraction_meta["short_horizontal_accepted_count"] >= 1
    assert len(h_rects) >= 2
    assert len(v_rects) >= 1
