from __future__ import annotations

import json
from pathlib import Path

from training.convert_resplan import convert_resplan_dataset
from training.materialize_dataset import materialize_manifest, materialize_splits

from tests.test_resplan_conversion import build_resplan_like_plan


def test_materialize_manifest_rewrites_paths_locally(tmp_path: Path):
    source_root = tmp_path / "source"
    convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}],
        source_root,
        limit=2,
        preview_limit=0,
    )

    materialized = materialize_manifest(
        manifest_path=source_root / "resplan_manifest.jsonl",
        output_root=tmp_path / "materialized",
        include_preview=False,
    )

    assert len(materialized) == 2
    first = materialized[0]
    assert "_manifest_path" not in first
    assert first["image_path"].startswith("samples/resplan/")
    assert (tmp_path / "materialized" / first["image_path"]).exists()
    assert first["preview_path"] is None


def test_materialize_splits_rewrites_entries(tmp_path: Path):
    source_root = tmp_path / "source"
    convert_resplan_dataset(
        [build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}],
        source_root,
        limit=2,
        preview_limit=0,
    )

    split_dir = tmp_path / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    with (source_root / "resplan_manifest.jsonl").open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entries.append(json.loads(line))

    for split_name, rows in {
        "train": [entries[0]],
        "val": [entries[1]],
        "test": [entries[0], entries[1]],
    }.items():
        with (split_dir / f"{split_name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    materialized = materialize_manifest(
        manifest_path=source_root / "resplan_manifest.jsonl",
        output_root=tmp_path / "materialized",
    )
    counts = materialize_splits(
        split_dir=split_dir,
        materialized_entries=materialized,
        output_root=tmp_path / "materialized",
    )

    assert counts == {"train": 1, "val": 1, "test": 2}
    train_entries = []
    with (tmp_path / "materialized" / "index" / "train.jsonl").open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                train_entries.append(json.loads(line))
    assert train_entries[0]["image_path"].startswith("samples/resplan/")


def test_materialize_manifest_can_resume_existing_files(tmp_path: Path):
    source_root = tmp_path / "source"
    convert_resplan_dataset(
        [build_resplan_like_plan()],
        source_root,
        limit=1,
        preview_limit=0,
    )

    output_root = tmp_path / "materialized"
    first = materialize_manifest(
        manifest_path=source_root / "resplan_manifest.jsonl",
        output_root=output_root,
    )
    image_path = output_root / first[0]["image_path"]
    before_size = image_path.stat().st_size

    second = materialize_manifest(
        manifest_path=source_root / "resplan_manifest.jsonl",
        output_root=output_root,
    )

    assert second[0]["image_path"] == first[0]["image_path"]
    assert image_path.stat().st_size == before_size


def test_copy_helper_resumes_partial_file(tmp_path: Path):
    from training.materialize_dataset import _copy_file_resilient

    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    data = bytes(range(256)) * 1024
    source.write_bytes(data)
    target.write_bytes(data[:4096])

    _copy_file_resilient(
        source,
        target,
        retries=1,
        chunk_size_bytes=1024,
        skip_existing=True,
    )

    assert target.read_bytes() == data
