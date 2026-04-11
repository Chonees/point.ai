from __future__ import annotations

import numpy as np

from ..observability import log_event
from .flood_fill import flood_fill_room_region, _build_closed_mask


def analyze_labeled_rooms(
    annotations: list[dict],
    wall_mask: np.ndarray,
    image_shape: tuple[int, int],
    *,
    labels: list[dict] | None = None,
    closed_mask: np.ndarray | None = None,
) -> dict[str, object]:
    """Resolve flood-filled room regions for every label and audit overlaps."""
    if labels is None:
        labels = [a for a in annotations if a.get("type") == "label"]
    if closed_mask is None:
        closed_mask = _build_closed_mask(annotations, wall_mask, image_shape)

    union_mask = np.zeros(image_shape, dtype=bool)
    rooms: list[dict[str, object]] = []
    duplicated_region_count = 0
    overlapping_label_count = 0

    for index, label in enumerate(labels):
        region = flood_fill_room_region(
                annotations,
                wall_mask,
                image_shape,
                int(float(label.get("x1", 0))),
                int(float(label.get("y1", 0))),
                closed_mask=closed_mask,
            )

        if not region:
            log_event(
                "room_region_skipped",
                index=index,
                room_name=label.get("roomName"),
                reason="room_region_not_found",
            )
            rooms.append(
                {
                    "index": index,
                    "label": label,
                    "room_name": label.get("roomName"),
                    "region": None,
                    "area_px": 0,
                    "bbox": None,
                    "seed": (int(float(label.get("x1", 0))), int(float(label.get("y1", 0)))),
                    "duplicate_of_index": None,
                    "overlap_area_px": 0,
                }
            )
            continue

        room_mask = region["mask"]
        bbox = tuple(int(v) for v in region["bbox"])
        area_px = int(region["area_px"])
        seed = tuple(int(v) for v in region["seed"])
        overlap_area_px = int(np.count_nonzero(union_mask & room_mask))
        if overlap_area_px > 0:
            overlapping_label_count += 1

        duplicate_of_index: int | None = None
        for previous in rooms:
            previous_region = previous.get("region")
            if previous_region is None:
                continue
            if int(previous["area_px"]) != area_px or tuple(previous["bbox"]) != bbox:
                continue
            if np.array_equal(previous_region["mask"], room_mask):
                duplicate_of_index = int(previous["index"])
                duplicated_region_count += 1
                break

        union_mask |= room_mask
        log_event(
            "room_region_detected",
            index=index,
            room_name=label.get("roomName"),
            seed={"x": seed[0], "y": seed[1]},
            bbox={"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
            area_pixels=area_px,
            overlap_area_px=overlap_area_px,
            duplicate_of_index=duplicate_of_index,
        )
        rooms.append(
            {
                "index": index,
                "label": label,
                "room_name": label.get("roomName"),
                "region": region,
                "area_px": area_px,
                "bbox": bbox,
                "seed": seed,
                "duplicate_of_index": duplicate_of_index,
                "overlap_area_px": overlap_area_px,
            }
        )

    raw_labeled_area_px = int(sum(int(room["area_px"]) for room in rooms))
    union_area_px = int(np.count_nonzero(union_mask))
    overlap_area_px = raw_labeled_area_px - union_area_px
    return {
        "rooms": rooms,
        "rooms_by_label_id": {id(room["label"]): room for room in rooms},
        "union_area_px": union_area_px,
        "raw_labeled_area_px": raw_labeled_area_px,
        "overlap_area_px": overlap_area_px,
        "overlapping_label_count": overlapping_label_count,
        "duplicated_region_count": duplicated_region_count,
        "closed_mask": closed_mask,
    }
