from __future__ import annotations

from pathlib import Path

from training.common import write_jsonl
from training.create_unified_index import build_dataset_splits, create_unified_index


def test_build_dataset_splits_is_reproducible():
    entries = [
        {"dataset": "resplan", "sample_id": f"r-{index:02d}"}
        for index in range(10)
    ] + [
        {"dataset": "cubicasa", "sample_id": f"c-{index:02d}"}
        for index in range(4)
    ]

    first = build_dataset_splits(entries, seed=9)
    second = build_dataset_splits(entries, seed=9)

    assert first == second
    assert len(first["train"]) > 0
    assert len(first["val"]) > 0
    assert len(first["test"]) > 0
    assert {entry["dataset"] for entry in first["train"]} == {"cubicasa", "resplan"}


def test_create_unified_index_writes_jsonl(tmp_path: Path):
    manifest_path = tmp_path / "manifest.jsonl"
    entries = [
        {"dataset": "resplan", "sample_id": "r-01"},
        {"dataset": "resplan", "sample_id": "r-02"},
        {"dataset": "resplan", "sample_id": "r-03"},
    ]
    write_jsonl(manifest_path, entries)

    splits = create_unified_index([manifest_path], tmp_path / "index", seed=5)

    assert (tmp_path / "index" / "train.jsonl").exists()
    assert (tmp_path / "index" / "val.jsonl").exists()
    assert (tmp_path / "index" / "test.jsonl").exists()
    assert (tmp_path / "index" / "summary.json").exists()
    assert sum(len(items) for items in splits.values()) == 3
