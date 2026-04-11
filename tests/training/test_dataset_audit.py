from __future__ import annotations

from pathlib import Path

import numpy as np

from training.common import ConvertedSample, save_converted_sample
from training.dataset_audit import audit_manifest
from training.convert_resplan import convert_resplan_plan

from tests.test_resplan_conversion import build_resplan_like_plan


def test_audit_manifest_scores_rich_sample(tmp_path: Path):
    sample = convert_resplan_plan(build_resplan_like_plan(), image_size=128, padding=6)
    entry = save_converted_sample(sample, tmp_path, write_preview=False)
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(__import__("json").dumps(entry) + "\n", encoding="utf-8")

    records, summary = audit_manifest(manifest_path, tmp_path / "audits")

    assert len(records) == 1
    assert records[0]["quality_score"] > 40
    assert "no_walls" not in records[0]["flags"]
    assert summary["sample_count"] == 1


def test_audit_manifest_flags_degenerate_sample(tmp_path: Path):
    sample = ConvertedSample(
        dataset="toy",
        sample_id="toy-0001",
        source_id="toy-0001",
        image=np.full((3, 64, 64), 255, dtype=np.uint8),
        label=np.zeros((2, 64, 64), dtype=np.uint8),
        heatmaps={channel: [] for channel in range(21)},
        scale=1.0,
        meta={},
    )
    entry = save_converted_sample(sample, tmp_path, write_preview=False)
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(__import__("json").dumps(entry) + "\n", encoding="utf-8")

    records, _ = audit_manifest(manifest_path, tmp_path / "audits")

    assert "no_walls" in records[0]["flags"]
    assert "no_rooms" in records[0]["flags"]
    assert records[0]["quality_score"] < 20
