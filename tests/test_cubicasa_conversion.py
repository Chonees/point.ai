from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from training.convert_cubicasa import (
    collect_cubicasa_entries,
    convert_cubicasa_dataset,
    convert_cubicasa_sample_dir,
)
from training.prepare_cubicasa_training import prepare_cubicasa_training


def _cubi_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".."
        / "floorplan-research"
        / "CubiCasa5k"
    ).resolve()


def build_fake_cubicasa_payload(size: int = 48) -> dict[str, object]:
    image = np.full((3, size, size), 255, dtype=np.uint8)
    image[:, 6:-6, 6:-6] = np.array([245, 245, 245], dtype=np.uint8).reshape(3, 1, 1)

    label = np.zeros((2, size, size), dtype=np.uint8)
    label[0, 5:-5, 5:-5] = 11
    label[0, 4:8, 4:-4] = 2
    label[0, -8:-4, 4:-4] = 2
    label[0, 4:-4, 4:8] = 2
    label[0, 4:-4, -8:-4] = 2
    label[1, 4:8, 18:28] = 1
    label[1, 24:30, 4:8] = 2

    heatmaps = {channel: [] for channel in range(21)}
    heatmaps[0] = [(4, 4)]
    heatmaps[1] = [(size - 5, 4)]
    heatmaps[2] = [(size - 5, size - 5)]
    heatmaps[3] = [(4, size - 5)]
    heatmaps[13] = [(18, 5)]
    heatmaps[14] = [(27, 5)]
    heatmaps[15] = [(5, 24)]
    heatmaps[16] = [(5, 29)]

    return {
        "image": image,
        "label": label,
        "heatmaps": heatmaps,
        "scale": 1.0,
        "meta": {
            "dataset": "cubicasa",
            "source_id": "0001",
            "relative_path": "high_quality/0001",
            "image_variant": "scaled",
            "image_shape": [size, size],
            "floor_scaled_images": ["F1_scaled.png"],
            "floor_original_images": ["F1_original.png"],
            "room_labels_present": [0, 2, 11],
            "icon_labels_present": [0, 1, 2],
            "heatmap_counts": {str(channel): len(coords) for channel, coords in heatmaps.items()},
        },
    }


def make_fake_cubicasa_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for split_name, relative_paths in {
        "train": ["/high_quality/0001/", "/high_quality/0002/"],
        "val": ["/colorful/0003/"],
        "test": ["/high_quality_architectural/0004/"],
    }.items():
        (root / f"{split_name}.txt").write_text("\n".join(relative_paths) + "\n", encoding="utf-8")

    for relative_path in (
        Path("high_quality/0001"),
        Path("high_quality/0002"),
        Path("colorful/0003"),
        Path("high_quality_architectural/0004"),
    ):
        sample_dir = root / relative_path
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "model.svg").write_text("<svg/>", encoding="utf-8")
        image = np.full((16, 16, 3), 255, dtype=np.uint8)
        cv2.imwrite(str(sample_dir / "F1_scaled.png"), image)
        cv2.imwrite(str(sample_dir / "F1_original.png"), image)

    return root


def test_collect_cubicasa_entries_reads_split_files(tmp_path: Path):
    root = make_fake_cubicasa_root(tmp_path / "cubicasa")
    entries = collect_cubicasa_entries(root)

    assert len(entries) == 4
    assert entries[0]["split"] == "train"
    assert entries[0]["relative_path"] == "high_quality/0001"
    assert {entry["split"] for entry in entries} == {"train", "val", "test"}


def test_convert_cubicasa_sample_dir_builds_training_sample(monkeypatch, tmp_path: Path):
    sample_dir = (tmp_path / "high_quality" / "0001")
    sample_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "training.convert_cubicasa._load_cubicasa_arrays",
        lambda sample_dir, use_original=False: build_fake_cubicasa_payload(),
    )

    sample = convert_cubicasa_sample_dir(
        sample_dir,
        split="train",
        relative_path="high_quality/0001",
        use_original=False,
    )

    assert sample.dataset == "cubicasa"
    assert sample.sample_id == "cubicasa-high_quality-0001"
    assert sample.source_id == "high_quality/0001"
    assert sample.image.shape == (3, 48, 48)
    assert sample.label.shape == (2, 48, 48)
    assert np.any(sample.label[0] == 2)
    assert np.any(sample.label[1] == 1)
    assert sample.meta["source_split"] == "train"
    assert sample.meta["source_partition"] == "high_quality"


def test_convert_cubicasa_dataset_writes_manifest(monkeypatch, tmp_path: Path):
    root = make_fake_cubicasa_root(tmp_path / "cubicasa")
    monkeypatch.setattr(
        "training.convert_cubicasa._load_cubicasa_arrays",
        lambda sample_dir, use_original=False: build_fake_cubicasa_payload(),
    )

    manifest = convert_cubicasa_dataset(root, tmp_path / "out", limit=3, preview_limit=1)

    assert len(manifest) == 3
    assert (tmp_path / "out" / "cubicasa_manifest.jsonl").exists()
    assert (tmp_path / "out" / "cubicasa_summary.json").exists()


def test_prepare_cubicasa_training_writes_complete_layout(monkeypatch, tmp_path: Path):
    root = make_fake_cubicasa_root(tmp_path / "cubicasa")
    monkeypatch.setattr(
        "training.convert_cubicasa._load_cubicasa_arrays",
        lambda sample_dir, use_original=False: build_fake_cubicasa_payload(),
    )

    summary = prepare_cubicasa_training(
        input_dir=root,
        output_root=tmp_path / "ready",
        limit=4,
        preview_limit=1,
        seed=3,
        use_original=False,
    )

    output_root = tmp_path / "ready"
    assert summary["converted_sample_count"] == 4
    assert (output_root / "converted" / "cubicasa_manifest.jsonl").exists()
    assert (output_root / "index" / "train.jsonl").exists()
    assert (output_root / "cubi_layout" / "train.txt").exists()
    assert (output_root / "cubi_layout" / "cubi_lmdb").exists()
    assert (output_root / "prepare_summary.json").exists()

    sys.path.insert(0, str(_cubi_root()))
    from floortrans.loaders import DictToTensor, FloorplanSVG

    dataset = FloorplanSVG(str(output_root / "cubi_layout") + "\\", "train.txt", format="lmdb")
    sample = dataset[0]
    assert sample["folder"].startswith("cubicasa-")
    assert sample["label"].shape[0] == 2

    training_dataset = FloorplanSVG(
        str(output_root / "cubi_layout") + "\\",
        "train.txt",
        format="lmdb",
        augmentations=DictToTensor(),
    )
    training_sample = training_dataset[0]
    assert training_sample["label"].shape[0] == 23
