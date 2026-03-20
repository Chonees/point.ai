"""
label_converter.py  —  converts a hand-painted / AI-painted TRAIN ONE.png
into the label.npy + heatmaps.json format that CubiCasa training expects.

Matches painted colors to class IDs using nearest-neighbor in RGB space.
Tolerant of slight color variations from AI painters.

Usage:
    python training/label_converter.py                        # all folders
    python training/label_converter.py --folder D:/PointAIData/dataset/0001
    python training/label_converter.py --preview              # save preview PNGs
    python training/label_converter.py --start 12 --end 221  # range of folders
"""
from __future__ import annotations

import argparse
import json
import numpy as np
import cv2
from pathlib import Path

# ---------------------------------------------------------------------------
# Color → class mapping
# ---------------------------------------------------------------------------

# Room segmentation classes (label channel)
ROOM_COLORS: list[tuple[tuple[int,int,int], int, str]] = [
    ((255, 255, 255),  0,  "background"),
    ((244, 249, 239),  1,  "outdoor"),
    ((32,  37,  45),   2,  "wall"),
    ((241, 231, 214),  3,  "kitchen"),
    ((250, 241, 221),  4,  "living"),
    ((233, 242, 255),  5,  "bedroom"),
    ((226, 241, 245),  6,  "bath"),
    ((240, 240, 240),  7,  "entry"),
    ((226, 226, 226),  8,  "railing"),
    ((237, 230, 239),  9,  "storage"),
    ((231, 233, 236),  10, "garage"),
    ((248, 248, 248),  11, "room"),
]

# Icon segmentation classes (separate channel)
ICON_COLORS: list[tuple[tuple[int,int,int], int, str]] = [
    ((255, 255, 255),  0,  "background"),
    ((69,  142, 255),  1,  "window"),
    ((214, 116, 47),   2,  "door"),
]

# Build numpy arrays for fast nearest-neighbor matching
_ROOM_PALETTE = np.array([c[0] for c in ROOM_COLORS], dtype=np.float32)   # (N, 3)
_ROOM_IDS     = np.array([c[1] for c in ROOM_COLORS], dtype=np.uint8)

_ICON_PALETTE = np.array([c[0] for c in ICON_COLORS], dtype=np.float32)
_ICON_IDS     = np.array([c[1] for c in ICON_COLORS], dtype=np.uint8)


def _nearest(pixels: np.ndarray, palette: np.ndarray, ids: np.ndarray) -> np.ndarray:
    """
    For each pixel (N,3) find the nearest color in palette → return class IDs (N,).
    Uses chunked processing to avoid OOM on large images.
    """
    h = pixels.shape[0]
    result = np.zeros(h, dtype=np.uint8)
    chunk = 50_000
    for start in range(0, h, chunk):
        end = min(start + chunk, h)
        diff = pixels[start:end, None, :] - palette[None, :, :]   # (C,N,3)
        dist = np.sum(diff ** 2, axis=2)                           # (C,N)
        result[start:end] = ids[np.argmin(dist, axis=1)]
    return result


def _separate_walls_from_doors(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Separate wall pixels from door arc pixels.

    Strategy:
    1. Dark pixels (R<80, G<80, B<80) → always walls — AI paints walls near-black
    2. Orange pixels (R>150, R-B>80) → ambiguous (could be wall or door)
       Apply thickness test: thick orange → wall, thin orange → door
    3. Blue pixels → windows (handled separately, not touched here)

    Returns (wall_mask, door_mask) as boolean arrays (H, W).
    """
    r = rgb[:,:,0].astype(int)
    g = rgb[:,:,1].astype(int)
    b = rgb[:,:,2].astype(int)

    # 1. Dark pixels = walls (painted near-black by AI)
    dark_wall = (r < 80) & (g < 80) & (b < 80)

    # 2. Orange pixels = ambiguous (wall boundary lines OR door arcs)
    orange = (r > 130) & (r - b > 80) & (g < 160)

    # Apply morphological thickness test on orange only
    ERODE_PX = 6  # walls ~10-20px thick; door arcs ~2-4px → 6px separates them
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ERODE_PX, ERODE_PX))
    orange_u8 = orange.astype(np.uint8)
    thick_orange = cv2.erode(orange_u8, kernel, iterations=1)
    thick_orange = cv2.dilate(thick_orange, kernel, iterations=1)

    orange_wall = thick_orange.astype(bool)   # thick orange → wall
    orange_door = orange & ~orange_wall        # thin orange → door arc

    wall_mask = dark_wall | orange_wall
    door_mask = orange_door

    return wall_mask, door_mask


def convert(label_path: Path, preview: bool = False) -> dict:
    """
    Convert TRAIN ONE.png → label.npy + heatmaps.json
    Returns dict with pixel counts per class.
    """
    img_bgr = cv2.imread(str(label_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot read {label_path}")

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    flat = rgb.astype(np.float32).reshape(-1, 3)

    # --- Separate thick walls from thin door arcs by morphology ---
    wall_mask, door_mask_morph = _separate_walls_from_doors(rgb)

    # --- Room label mask (nearest color) ---
    room_flat = _nearest(flat, _ROOM_PALETTE, _ROOM_IDS)
    room_mask = room_flat.reshape(h, w)

    # Override: thick orange/dark regions → wall class regardless of color match
    room_mask[wall_mask] = 2   # wall

    # --- Icon label mask ---
    icon_flat = _nearest(flat, _ICON_PALETTE, _ICON_IDS)
    icon_mask = icon_flat.reshape(h, w)

    # Override: thin orange regions → door class; thick → clear icon (already wall)
    icon_mask[door_mask_morph] = 2   # door
    icon_mask[wall_mask]       = 0   # not an icon, it's a wall

    # --- Stack into (2, H, W) label array ---
    label = np.stack([room_mask, icon_mask], axis=0)   # channel 0=room, 1=icon

    # --- Heatmaps: junction points from wall mask ---
    heatmaps = _detect_junctions(room_mask)

    # --- Save ---
    out_dir = label_path.parent
    np.save(str(out_dir / "label.npy"), label)
    (out_dir / "heatmaps.json").write_text(
        json.dumps({str(k): v for k, v in heatmaps.items()}, indent=2),
        encoding="utf-8"
    )

    # --- Optional preview ---
    if preview:
        _save_preview(out_dir, rgb.astype(np.uint8), room_mask, icon_mask, heatmaps)

    # --- Stats ---
    stats = {}
    for _, cid, name in ROOM_COLORS:
        stats[name] = int(np.sum(room_mask == cid))
    for _, cid, name in ICON_COLORS[1:]:  # skip background
        stats[name] = int(np.sum(icon_mask == cid))
    return stats


# ---------------------------------------------------------------------------
# Junction detection from wall mask
# ---------------------------------------------------------------------------
def _detect_junctions(wall_mask: np.ndarray) -> dict[int, list[list[int]]]:
    """
    Detect L / T / X junction points from wall binary mask.
    Returns heatmaps dict: {channel_id: [[x,y], ...]}
    Channels: 0=L-junction, 1=T-junction, 2=X-junction
    """
    binary = (wall_mask == 2).astype(np.uint8) * 255

    # Skeletonize
    from skimage.morphology import skeletonize
    skel = skeletonize(binary > 0).astype(np.uint8)

    junctions: dict[int, list[list[int]]] = {0: [], 1: [], 2: []}

    # For each skeleton pixel count its neighbors
    ys, xs = np.where(skel > 0)
    for y, x in zip(ys, xs):
        if y == 0 or y >= skel.shape[0]-1 or x == 0 or x >= skel.shape[1]-1:
            continue
        neighborhood = skel[y-1:y+2, x-1:x+2].copy()
        neighborhood[1, 1] = 0
        n = int(neighborhood.sum())
        if n == 2:
            junctions[0].append([int(x), int(y)])   # L-junction
        elif n == 3:
            junctions[1].append([int(x), int(y)])   # T-junction
        elif n >= 4:
            junctions[2].append([int(x), int(y)])   # X-junction

    return junctions


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
_PREVIEW_ROOM = {
    0: (255,255,255), 1: (244,249,239), 2: (32,37,45),
    3: (241,231,214), 4: (250,241,221), 5: (233,242,255),
    6: (226,241,245), 7: (240,240,240), 8: (226,226,226),
    9: (237,230,239), 10: (231,233,236), 11: (248,248,248),
}

def _save_preview(out_dir: Path, original: np.ndarray,
                  room_mask: np.ndarray, icon_mask: np.ndarray,
                  heatmaps: dict) -> None:
    h, w = room_mask.shape
    preview = np.zeros((h, w, 3), dtype=np.uint8)
    for cid, color in _PREVIEW_ROOM.items():
        preview[room_mask == cid] = color

    # Overlay windows (blue) and doors (orange)
    preview[icon_mask == 1] = (69, 142, 255)
    preview[icon_mask == 2] = (214, 116, 47)

    # Draw junction points
    colors = [(0,255,0), (255,255,0), (255,0,0)]
    for ch, pts in heatmaps.items():
        for x, y in pts[:500]:
            cv2.circle(preview, (x, y), 2, colors[ch], -1)

    cv2.imwrite(
        str(out_dir / "preview.png"),
        cv2.cvtColor(preview, cv2.COLOR_RGB2BGR)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="D:/PointAIData/dataset",
                        help="Root dataset folder")
    parser.add_argument("--folder", default=None,
                        help="Process a single folder instead of all")
    parser.add_argument("--preview", action="store_true",
                        help="Save preview.png for visual inspection")
    parser.add_argument("--start",     type=int, default=1)
    parser.add_argument("--end",       type=int, default=9999)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.folder:
        folders = [Path(args.folder)]
    else:
        folders = sorted(
            f for f in Path(args.dataset).iterdir()
            if f.is_dir() and f.name.isdigit() and args.start <= int(f.name) <= args.end
        )

    label_name = "TRAIN ONE.png"
    done = skipped = errors = 0

    for folder in folders:
        label_path = folder / label_name
        if not label_path.exists():
            skipped += 1
            continue

        npy_path = folder / "label.npy"
        if npy_path.exists() and not args.overwrite:
            skipped += 1
            continue

        try:
            stats = convert(label_path, preview=args.preview)
            walls   = stats.get("wall", 0)
            windows = stats.get("window", 0)
            doors   = stats.get("door", 0)
            print(f"  {folder.name}  walls={walls}  windows={windows}  doors={doors}")
            done += 1
        except Exception as e:
            print(f"  {folder.name}  ERROR: {e}")
            errors += 1

    print(f"\nDone: {done}  Skipped: {skipped}  Errors: {errors}")


if __name__ == "__main__":
    main()
