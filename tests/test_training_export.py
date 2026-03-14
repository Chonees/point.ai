from __future__ import annotations

import sys
from pathlib import Path

from training.convert_resplan import convert_resplan_dataset
from training.create_unified_index import create_unified_index
from training.export_lmdb import export_splits_to_cubi_layout
from training.prepare_resplan_training import prepare_resplan_training

from tests.test_resplan_conversion import build_resplan_like_plan


def _cubi_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".."
        / "floorplan-research"
        / "CubiCasa5k"
    ).resolve()


def test_export_lmdb_is_loadable_by_cubicasa_loader(tmp_path: Path):
    converted_dir = tmp_path / "converted"
    index_dir = tmp_path / "index"
    cubi_dir = tmp_path / "cubi"

    convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}, {**build_resplan_like_plan(), "id": 9}],
        converted_dir,
        limit=3,
        preview_limit=0,
    )
    manifest_path = converted_dir / "resplan_manifest.jsonl"
    create_unified_index([manifest_path], index_dir, seed=11)
    export_splits_to_cubi_layout(
        manifest_path=manifest_path,
        split_dir=index_dir,
        output_dir=cubi_dir,
        overwrite=True,
    )

    sys.path.insert(0, str(_cubi_root()))
    from floortrans.loaders import FloorplanSVG, DictToTensor

    dataset = FloorplanSVG(str(cubi_dir) + "\\", "train.txt", format="lmdb")
    sample = dataset[0]
    assert sample["image"].shape[0] == 3
    assert sample["label"].shape[0] == 2
    assert sample["folder"].startswith("resplan-")

    training_dataset = FloorplanSVG(
        str(cubi_dir) + "\\",
        "train.txt",
        format="lmdb",
        augmentations=DictToTensor(),
    )
    training_sample = training_dataset[0]
    assert training_sample["image"].shape[0] == 3
    assert training_sample["label"].shape[0] == 23


def test_prepare_resplan_training_writes_complete_layout(tmp_path: Path):
    input_path = tmp_path / "mock_resplan.pkl"

    import pickle

    with input_path.open("wb") as handle:
        pickle.dump(
            [
                build_resplan_like_plan(),
                {**build_resplan_like_plan(), "id": 8},
                {**build_resplan_like_plan(), "id": 9},
            ],
            handle,
        )

    summary = prepare_resplan_training(
        input_path=input_path,
        output_root=tmp_path / "ready",
        limit=3,
        image_size=96,
        padding=4,
        preview_limit=1,
        seed=3,
    )

    output_root = tmp_path / "ready"
    assert summary["converted_sample_count"] == 3
    assert (output_root / "converted" / "resplan_manifest.jsonl").exists()
    assert (output_root / "index" / "train.jsonl").exists()
    assert (output_root / "cubi_layout" / "train.txt").exists()
    assert (output_root / "cubi_layout" / "cubi_lmdb").exists()
    assert (output_root / "prepare_summary.json").exists()
