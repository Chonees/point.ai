from __future__ import annotations

import io
import tarfile
from pathlib import Path

from PIL import Image

from training.convert_floorplancad import convert_floorplancad_dataset
from training.convert_resplan import convert_resplan_dataset
from training.prepare_combined_training import prepare_combined_training

from tests.test_floorplancad_conversion import build_floorplancad_image, build_floorplancad_svg
from tests.test_resplan_conversion import build_resplan_like_plan


def test_prepare_combined_training_writes_layout(tmp_path: Path):
    resplan_dir = tmp_path / "resplan"
    floor_dir = tmp_path / "floor"
    archive_path = tmp_path / "train-00.tar.xz"

    convert_resplan_dataset([build_resplan_like_plan(), {**build_resplan_like_plan(), "id": 8}], resplan_dir, limit=2, preview_limit=0)

    image = Image.fromarray(build_floorplancad_image(128))
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    with tarfile.open(archive_path, "w:xz") as archive:
        svg_data = build_floorplancad_svg().encode("utf-8")
        svg_info = tarfile.TarInfo(name="0000-0001.svg")
        svg_info.size = len(svg_data)
        archive.addfile(svg_info, io.BytesIO(svg_data))
        png_data = image_bytes.getvalue()
        png_info = tarfile.TarInfo(name="0000-0001.png")
        png_info.size = len(png_data)
        archive.addfile(png_info, io.BytesIO(png_data))

    convert_floorplancad_dataset(tmp_path, floor_dir, limit=1, preview_limit=0)

    summary = prepare_combined_training(
        manifests=[
            resplan_dir / "resplan_manifest.jsonl",
            floor_dir / "floorplancad_manifest.jsonl",
        ],
        output_root=tmp_path / "combined",
        seed=7,
    )

    assert sum(summary["split_counts"].values()) == 3
    assert (tmp_path / "combined" / "cubi_layout" / "train.txt").exists()
    assert (tmp_path / "combined" / "cubi_layout" / "cubi_lmdb").exists()
    assert (tmp_path / "combined" / "prepare_summary.json").exists()
