"""Download model weights from HuggingFace at container startup."""
import os
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "chonees/pointai-weights"
WEIGHTS_DIR = Path("/app/weights")
CUBICASA_DIR = Path("/app/cubicasa")

def main():
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("WARNING: HF_TOKEN not set, skipping weight download")
        return

    mitunet_path = Path(os.environ.get("POINTAI_MITUNET_WEIGHTS", ""))
    cubicasa_weights = CUBICASA_DIR / "model_best_val_loss_var.pkl"
    floortrans_dir = CUBICASA_DIR / "floortrans"

    if mitunet_path.exists() and cubicasa_weights.exists() and floortrans_dir.exists():
        print("Weights already downloaded, skipping.")
        return

    print(f"Downloading weights from {REPO_ID}...")
    local_dir = snapshot_download(REPO_ID, local_dir=str(WEIGHTS_DIR), token=token)
    print(f"Downloaded to {local_dir}")

    # Organize CubiCasa files
    CUBICASA_DIR.mkdir(parents=True, exist_ok=True)

    src_weights = WEIGHTS_DIR / "cubicasa_model_best_val_loss_var.pkl"
    if src_weights.exists() and not cubicasa_weights.exists():
        shutil.copy2(str(src_weights), str(cubicasa_weights))
        print(f"Copied CubiCasa weights to {cubicasa_weights}")

    src_floortrans = WEIGHTS_DIR / "floortrans"
    if src_floortrans.exists() and not floortrans_dir.exists():
        shutil.copytree(str(src_floortrans), str(floortrans_dir))
        print(f"Copied floortrans to {floortrans_dir}")

    print("Weights ready!")

if __name__ == "__main__":
    main()
