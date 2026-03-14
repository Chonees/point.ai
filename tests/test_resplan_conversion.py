from __future__ import annotations

from pathlib import Path

import numpy as np
from shapely.geometry import MultiPolygon, box

from training.common import save_converted_sample
from training.convert_resplan import convert_resplan_dataset, convert_resplan_plan


def build_resplan_like_plan() -> dict[str, object]:
    outer = box(0, 0, 256, 200)
    inner = box(10, 10, 246, 190)
    wall = outer.difference(inner)

    return {
        "id": 7,
        "unitType": "pilot",
        "wall_depth": 4.0,
        "area": 420.0,
        "net_area": 380.0,
        "wall": wall,
        "inner": MultiPolygon([inner]),
        "living": MultiPolygon([box(18, 18, 118, 90)]),
        "bedroom": MultiPolygon([box(128, 18, 226, 90)]),
        "bathroom": MultiPolygon([box(18, 104, 72, 160)]),
        "kitchen": MultiPolygon([box(82, 104, 162, 180)]),
        "storage": MultiPolygon([box(172, 104, 226, 150)]),
        "balcony": MultiPolygon([box(180, 190, 246, 220)]),
        "veranda": MultiPolygon(),
        "garden": MultiPolygon(),
        "land": MultiPolygon(),
        "parking": MultiPolygon(),
        "pool": MultiPolygon(),
        "window": MultiPolygon([box(52, 0, 84, 8), box(246, 40, 256, 70)]),
        "door": MultiPolygon([box(118, 54, 130, 74)]),
        "front_door": box(110, 190, 138, 200),
        "stair": MultiPolygon(),
    }


def test_convert_resplan_plan_builds_training_sample():
    sample = convert_resplan_plan(build_resplan_like_plan(), image_size=128, padding=6)

    assert sample.dataset == "resplan"
    assert sample.sample_id == "resplan-00007"
    assert sample.image.shape == (3, 128, 128)
    assert sample.label.shape == (2, 128, 128)
    assert sample.image.dtype == np.uint8
    assert sample.label.dtype == np.uint8
    assert np.any(sample.label[0] == 2)
    assert np.any(sample.label[0] == 4)
    assert np.any(sample.label[1] == 1)
    assert np.any(sample.label[1] == 2)
    assert any(sample.heatmaps[channel] for channel in range(13))
    assert any(sample.heatmaps[channel] for channel in range(13, 17))


def test_save_and_manifest_round_trip(tmp_path: Path):
    sample = convert_resplan_plan(build_resplan_like_plan())
    entry = save_converted_sample(sample, tmp_path, write_preview=True)

    assert (tmp_path / entry["image_path"]).exists()
    assert (tmp_path / entry["label_path"]).exists()
    assert (tmp_path / entry["heatmaps_path"]).exists()
    assert (tmp_path / entry["meta_path"]).exists()
    assert (tmp_path / entry["preview_path"]).exists()


def test_convert_resplan_dataset_writes_manifest(tmp_path: Path):
    manifest = convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}],
        tmp_path,
        limit=2,
        image_size=96,
        preview_limit=1,
    )

    assert len(manifest) == 2
    assert (tmp_path / "resplan_manifest.jsonl").exists()
    assert (tmp_path / "resplan_summary.json").exists()
