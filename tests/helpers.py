import base64

import cv2
import numpy as np


def build_synthetic_structure_image() -> str:
    image = np.full((160, 220, 3), 255, dtype=np.uint8)

    # Outer walls
    cv2.rectangle(image, (20, 20), (200, 28), (0, 0, 0), -1)
    cv2.rectangle(image, (20, 132), (200, 140), (0, 0, 0), -1)
    cv2.rectangle(image, (20, 20), (28, 140), (0, 0, 0), -1)
    cv2.rectangle(image, (192, 20), (200, 140), (0, 0, 0), -1)

    # Interior wall
    cv2.rectangle(image, (106, 28), (114, 132), (0, 0, 0), -1)

    # Colored openings replace a wall fragment so the local heuristic can see them explicitly.
    cv2.rectangle(image, (106, 60), (114, 88), (0, 200, 0), -1)   # door on interior wall
    cv2.rectangle(image, (136, 20), (166, 28), (255, 0, 0), -1)   # window on top wall

    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def data_uri_to_base64_payload(data_uri: str) -> str:
    return data_uri.split(",", 1)[1] if "," in data_uri else data_uri


def build_manual_structure(*, source: str = "fixture/manual", with_openings: bool = True) -> dict:
    walls = [
        {
            "id": "wall-top",
            "orientation": "horizontal",
            "polyline": [{"x": 20.0, "y": 20.0}, {"x": 200.0, "y": 20.0}],
            "thickness": 8.0,
            "is_exterior": True,
            "confidence": 0.95,
        },
        {
            "id": "wall-bottom",
            "orientation": "horizontal",
            "polyline": [{"x": 20.0, "y": 140.0}, {"x": 200.0, "y": 140.0}],
            "thickness": 8.0,
            "is_exterior": True,
            "confidence": 0.95,
        },
        {
            "id": "wall-left",
            "orientation": "vertical",
            "polyline": [{"x": 20.0, "y": 20.0}, {"x": 20.0, "y": 140.0}],
            "thickness": 8.0,
            "is_exterior": True,
            "confidence": 0.95,
        },
        {
            "id": "wall-right",
            "orientation": "vertical",
            "polyline": [{"x": 200.0, "y": 20.0}, {"x": 200.0, "y": 140.0}],
            "thickness": 8.0,
            "is_exterior": True,
            "confidence": 0.95,
        },
        {
            "id": "wall-interior",
            "orientation": "vertical",
            "polyline": [{"x": 110.0, "y": 20.0}, {"x": 110.0, "y": 140.0}],
            "thickness": 8.0,
            "is_exterior": False,
            "confidence": 0.9,
        },
    ]

    openings = []
    if with_openings:
        openings = [
            {
                "id": "opening-door",
                "kind": "door",
                "wall_id": "wall-interior",
                "position": {"x": 110.0, "y": 74.0},
                "span": 28.0,
                "orientation": "vertical",
                "confidence": 0.9,
                "door_type": "normal",
            },
            {
                "id": "opening-window",
                "kind": "window",
                "wall_id": "wall-top",
                "position": {"x": 151.0, "y": 20.0},
                "span": 30.0,
                "orientation": "horizontal",
                "confidence": 0.92,
            },
        ]

    return {
        "model": "Fixture Structure",
        "source": source,
        "walls": walls,
        "openings": openings,
        "structure_meta": {
            "image_size": {"width": 220, "height": 160},
            "scale_status": "unverified",
            "unit": "pixel",
        },
        "inference_debug": {
            "backend": source,
            "raw_wall_fragments": len(walls),
            "raw_opening_detections": len(openings),
        },
    }


def build_low_quality_structure() -> dict:
    structure = build_manual_structure(source="fixture/low_quality", with_openings=False)
    for wall in structure["walls"]:
        wall["is_exterior"] = False
    return structure


def build_mitunet_infer_result() -> dict:
    structure = build_manual_structure(source="mitunet_local", with_openings=False)
    h, w = 160, 220
    wall_mask = np.zeros((h, w), dtype=np.uint8)

    cv2.rectangle(wall_mask, (20, 20), (120, 30), 255, -1)
    cv2.rectangle(wall_mask, (20, 60), (120, 70), 255, -1)
    cv2.rectangle(wall_mask, (150, 20), (160, 120), 255, -1)
    cv2.rectangle(wall_mask, (180, 20), (190, 120), 255, -1)

    structure["source"] = "mitunet_local"
    structure.setdefault("inference_debug", {})
    structure["inference_debug"]["backend"] = "mitunet_local"
    structure["inference_debug"]["model_variant"] = "mitunet"
    structure["_wall_mask"] = wall_mask
    structure["_image_shape"] = (h, w)
    return structure
