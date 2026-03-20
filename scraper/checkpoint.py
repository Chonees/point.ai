"""
checkpoint.py  —  atomic JSON persistence for index and visited-pages.

Uses write-to-tmp + rename for crash safety.
Retries on Windows PermissionError (OneDrive file locking).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR   = Path(__file__).resolve().parent.parent / "data" / "builder_plans"
INDEX_FILE   = OUTPUT_DIR / "index.json"
VISITED_FILE = OUTPUT_DIR / "visited_pages.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load(path: Path, default):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    for _ in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_index() -> list[dict]:
    return _load(INDEX_FILE, [])


def save_index(index: list[dict]) -> None:
    _save(INDEX_FILE, index)


def load_visited() -> set[str]:
    return set(_load(VISITED_FILE, []))


def save_visited(visited: set[str]) -> None:
    _save(VISITED_FILE, list(visited))
