from __future__ import annotations

import tempfile
from pathlib import Path
import os
import json

from ..cad_workspace.extractor import extract_cad_file
from ..cad_workspace.exporter import export_overlay_dxf


CAD_WORKSPACE_DIR = Path(tempfile.gettempdir()) / "pointai_cad_workspace"
CAD_WORKSPACE_DIR.mkdir(exist_ok=True)


def extract_cad_workspace(*, filename: str, data: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".dxf", ".dwg"}:
        raise ValueError("Only .dxf and .dwg files are supported.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(data)
        temp_path = Path(handle.name)

    try:
        result = extract_cad_file(temp_path, source_name=Path(filename).name)
        _save_analysis_snapshot(result)
        return result
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def export_cad_workspace_overlay(*, analysis_id: str) -> tuple[Path, str]:
    analysis_path = CAD_WORKSPACE_DIR / f"{analysis_id}.json"
    if not analysis_path.exists():
        raise FileNotFoundError(analysis_id)

    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    output_name = f"{analysis_id}-overlay.dxf"
    output_path = CAD_WORKSPACE_DIR / output_name
    export_overlay_dxf(payload, output_path)
    return output_path, output_name


def _save_analysis_snapshot(result: dict) -> None:
    analysis_id = str(result.get("analysis_id") or "").strip()
    if not analysis_id:
        return
    analysis_path = CAD_WORKSPACE_DIR / f"{analysis_id}.json"
    analysis_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
