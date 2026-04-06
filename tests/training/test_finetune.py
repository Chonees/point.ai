from __future__ import annotations

import json
import pickle
from pathlib import Path

import torch

from training.finetune import _normalize_num_workers, run_finetune
from training.prepare_resplan_training import prepare_resplan_training

from tests.test_resplan_conversion import build_resplan_like_plan


def test_run_finetune_writes_checkpoints_and_summary(tmp_path: Path):
    input_path = tmp_path / "mock_resplan.pkl"
    with input_path.open("wb") as handle:
        pickle.dump(
            [
                build_resplan_like_plan(),
                {**build_resplan_like_plan(), "id": 8},
                {**build_resplan_like_plan(), "id": 9},
            ],
            handle,
        )

    ready_root = tmp_path / "ready"
    prepare_resplan_training(
        input_path=input_path,
        output_root=ready_root,
        limit=3,
        image_size=96,
        padding=4,
        preview_limit=0,
        seed=3,
    )

    run_dir = tmp_path / "run"
    summary = run_finetune(
        data_path=ready_root / "cubi_layout",
        run_dir=run_dir,
        epochs=1,
        batch_size=2,
        image_size=128,
        learning_rate=1e-4,
        weight_decay=1e-4,
        device_name="cpu",
        num_workers=2,
        seed=7,
        init_weights=None,
        max_train_steps_per_epoch=1,
        max_val_steps=1,
        accumulation_steps=1,
        grad_clip_norm=1.0,
        amp_enabled=False,
        enable_color_jitter=False,
        model_variant="baseline",
        export_inference_checkpoint=run_dir / "checkpoints" / "best_inference.pt",
    )

    assert summary["global_step"] == 1
    assert Path(summary["latest_checkpoint"]).exists()
    assert Path(summary["best_checkpoint"]).exists()
    assert Path(summary["best_inference_checkpoint"]).exists()
    assert (run_dir / "history.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["num_workers"] == 2
    assert config["effective_num_workers"] == _normalize_num_workers(2)

    checkpoint = torch.load(summary["best_inference_checkpoint"], map_location="cpu", weights_only=False)
    assert checkpoint["variant"] == "baseline"
    assert "model_state" in checkpoint
