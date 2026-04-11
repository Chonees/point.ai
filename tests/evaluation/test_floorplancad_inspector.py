from __future__ import annotations

import tarfile
from pathlib import Path

from training.inspect_floorplancad import inspect_archive


def test_inspect_archive_summarizes_members(tmp_path: Path):
    archive_path = tmp_path / "sample.tar.xz"
    image_path = tmp_path / "example.png"
    annotation_path = tmp_path / "example.json"
    image_path.write_bytes(b"png")
    annotation_path.write_text("{}", encoding="utf-8")

    with tarfile.open(archive_path, "w:xz") as archive:
        archive.add(image_path, arcname="coco_vis/example.png")
        archive.add(annotation_path, arcname="annotations/example.json")

    report = inspect_archive(archive_path, scan_limit=50)

    assert report["members_scanned"] == 2
    assert "coco_vis" in report["top_level_dirs"]
    assert ".png" in report["extension_counts"]
    assert ".json" in report["extension_counts"]
    assert report["annotation_like_members"] == ["annotations/example.json"]
