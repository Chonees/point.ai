"""Copy pointai samples (that have label.npy) to combined dataset format."""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
import cv2, numpy as np

from training.common import save_converted_sample, write_jsonl
from training.prepare_pointai_training import load_sample

DATASET = Path("D:/PointAIData/dataset")
OUTPUT = Path("C:/PointAIData/combined_dataset/cubicasa")


def main():
    folders = sorted(
        f for f in DATASET.iterdir()
        if f.is_dir() and f.name.isdigit() and (f / "label.npy").exists()
    )
    print(f"Found {len(folders)} labeled folders")

    manifest = []
    done = skipped = errors = 0

    for folder in folders:
        sample_id = f"pointai-{folder.name}"
        out_dir = OUTPUT / "pointai" / sample_id
        if (out_dir / "label.npy").exists():
            # Already converted, just add to manifest
            try:
                label = np.load(str(out_dir / "label.npy"))
                img = cv2.imread(str(out_dir / "image.png"))
                if img is not None:
                    h, w = img.shape[:2]
                    manifest.append({
                        "dataset": "pointai",
                        "sample_id": sample_id,
                        "source_id": folder.name,
                        "image_path": f"pointai/{sample_id}/image.png",
                        "label_path": f"pointai/{sample_id}/label.npy",
                        "heatmaps_path": f"pointai/{sample_id}/heatmaps.json",
                        "image_shape": [3, h, w],
                        "label_shape": list(label.shape),
                        "scale": 1.0,
                    })
                    skipped += 1
                    continue
            except:
                pass

        sample = load_sample(folder)
        if sample is None:
            errors += 1
            continue

        try:
            record = save_converted_sample(sample, OUTPUT, write_preview=False)
            manifest.append(record)
            done += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR {folder.name}: {e}")

        if (done + skipped) % 20 == 0:
            print(f"  Progress: done={done} skipped(existing)={skipped} errors={errors} total={done+skipped+errors}/{len(folders)}")

    manifest_path = OUTPUT / "pointai_manifest.jsonl"
    write_jsonl(manifest_path, manifest)
    print(f"\nDone: {done}  Skipped(existing): {skipped}  Errors: {errors}")
    print(f"Manifest: {manifest_path} ({len(manifest)} entries)")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
