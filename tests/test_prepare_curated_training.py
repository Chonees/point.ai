from __future__ import annotations

from pathlib import Path

from training.convert_resplan import convert_resplan_dataset
from training.prepare_curated_training import prepare_curated_training

from tests.test_resplan_conversion import build_resplan_like_plan


def test_prepare_curated_training_filters_bad_samples(tmp_path: Path):
    good_dir = tmp_path / "good"
    bad_dir = tmp_path / "bad"

    convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}],
        good_dir,
        limit=2,
        preview_limit=0,
    )

    # Make a degenerate manifest by reusing a converted sample and blanking labels.
    bad_manifest_dir = bad_dir / "degenerate"
    bad_manifest_dir.mkdir(parents=True, exist_ok=True)
    (bad_manifest_dir / "image.png").write_bytes((good_dir / "resplan" / "resplan-00007" / "image.png").read_bytes())
    import numpy as np
    np.save(bad_manifest_dir / "label.npy", np.zeros((2, 64, 64), dtype=np.uint8))
    (bad_manifest_dir / "heatmaps.json").write_text("{}", encoding="utf-8")
    (bad_manifest_dir / "meta.json").write_text("{}", encoding="utf-8")
    bad_entry = {
        "dataset": "resplan",
        "sample_id": "resplan-bad",
        "source_id": "bad",
        "image_path": "degenerate/image.png",
        "label_path": "degenerate/label.npy",
        "heatmaps_path": "degenerate/heatmaps.json",
        "meta_path": "degenerate/meta.json",
        "preview_path": None,
        "scale": 1.0,
        "image_shape": [3, 64, 64],
        "label_shape": [2, 64, 64],
    }
    bad_manifest = bad_dir / "resplan_manifest.jsonl"
    bad_manifest.write_text(__import__("json").dumps(bad_entry) + "\n", encoding="utf-8")

    summary = prepare_curated_training(
        manifests=[good_dir / "resplan_manifest.jsonl", bad_manifest],
        output_root=tmp_path / "curated",
        seed=5,
        min_score=20,
    )

    assert summary["total_kept"] == 2
    assert summary["dropped_counts"]["resplan"] == 1
    assert (tmp_path / "curated" / "combined_manifest.jsonl").exists()
    assert (tmp_path / "curated" / "cubi_layout" / "train.txt").exists()


def test_prepare_curated_training_can_skip_layout_export(tmp_path: Path):
    good_dir = tmp_path / "good"

    convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}],
        good_dir,
        limit=2,
        preview_limit=0,
    )

    summary = prepare_curated_training(
        manifests=[good_dir / "resplan_manifest.jsonl"],
        output_root=tmp_path / "curated",
        seed=5,
        min_score=20,
        export_layout=False,
    )

    assert summary["total_kept"] == 2
    assert summary["export_layout"] is False
    assert summary["cubi_layout"] is None
    assert (tmp_path / "curated" / "combined_manifest.jsonl").exists()
    assert (tmp_path / "curated" / "index" / "train.jsonl").exists()
    assert not (tmp_path / "curated" / "cubi_layout").exists()
