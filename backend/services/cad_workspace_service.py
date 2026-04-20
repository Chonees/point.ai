from __future__ import annotations

import tempfile
from pathlib import Path
import os

from ..cad_workspace.extractor import extract_cad_file


def extract_cad_workspace(*, filename: str, data: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".dxf", ".dwg"}:
        raise ValueError("Only .dxf and .dwg files are supported.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(data)
        temp_path = Path(handle.name)

    try:
        return extract_cad_file(temp_path, source_name=Path(filename).name)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
