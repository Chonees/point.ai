from __future__ import annotations

import io
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image

from training.convert_floorplancad import convert_floorplancad_dataset, convert_floorplancad_sample


def build_floorplancad_svg() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" viewBox="0 0 100 100">
      <g inkscape:label="WALL">
        <path semantic-id="1" stroke="rgb(0,0,0)" fill="none" d="M 10,10 L 90,10 L 90,90 L 10,90 L 10,10"/>
      </g>
      <g inkscape:label="WINDOW">
        <path semantic-id="3" stroke="rgb(0,178,178)" fill="none" d="M 30,10 L 50,10"/>
      </g>
      <g inkscape:label="DOOR_FIRE">
        <path semantic-id="4" stroke="rgb(0,178,178)" fill="none" d="M 60,90 L 70,80"/>
        <path semantic-id="4" stroke="rgb(0,178,178)" fill="none" d="M 60,90 A 10,10 0 0,0 70,80"/>
      </g>
    </svg>
    """


def build_floorplancad_image(size: int = 256) -> np.ndarray:
    image = np.full((size, size, 3), 255, dtype=np.uint8)
    image[20:236, 20:236] = (245, 245, 245)
    return image


def test_convert_floorplancad_sample_builds_masks_and_heatmaps():
    sample = convert_floorplancad_sample(
        image_rgb=build_floorplancad_image(),
        svg_text=build_floorplancad_svg(),
        sample_stem="demo-001",
        archive_name="train-00.tar.xz",
    )

    assert sample.dataset == "floorplancad"
    assert sample.image.shape == (3, 256, 256)
    assert sample.label.shape == (2, 256, 256)
    assert np.any(sample.label[0] == 2)
    assert np.any(sample.label[0] == 11)
    assert np.any(sample.label[1] == 1)
    assert np.any(sample.label[1] == 2)
    assert any(sample.heatmaps[channel] for channel in range(13))
    assert any(sample.heatmaps[channel] for channel in range(13, 17))
    assert "WALL" in sample.meta["active_layers"]


def test_convert_floorplancad_dataset_writes_manifest(tmp_path: Path):
    archive_path = tmp_path / "train-00.tar.xz"
    svg_name = "0000-0001.svg"
    png_name = "0000-0001.png"

    image = Image.fromarray(build_floorplancad_image(128))
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    with tarfile.open(archive_path, "w:xz") as archive:
        svg_data = build_floorplancad_svg().encode("utf-8")
        svg_info = tarfile.TarInfo(name=svg_name)
        svg_info.size = len(svg_data)
        archive.addfile(svg_info, io.BytesIO(svg_data))

        png_data = image_bytes.getvalue()
        png_info = tarfile.TarInfo(name=png_name)
        png_info.size = len(png_data)
        archive.addfile(png_info, io.BytesIO(png_data))

    manifest = convert_floorplancad_dataset(tmp_path, tmp_path / "out", limit=1, preview_limit=1)

    assert len(manifest) == 1
    assert (tmp_path / "out" / "floorplancad_manifest.jsonl").exists()
    assert (tmp_path / "out" / "floorplancad_summary.json").exists()
