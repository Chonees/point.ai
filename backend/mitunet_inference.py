"""
mitunet_inference.py — backward-compatibility re-export barrel.

All logic has moved to backend/mitunet/. This module re-exports everything
so existing imports continue to work without modification.
"""
from .mitunet import (
    MITUNET_BACKEND,
    MITUNET_MASK_REGIONS_DXF_MODE,
    MAX_MITUNET_REGION_WALL_THICKNESS,
    MITUNET_MODEL_NAME,
    mitunet_available,
    infer_mitunet,
    build_mitunet_region_plan,
    align_opening_annotations_to_walls,
    regions_to_wall_annotations,
    generate_mitunet_region_dxf,
    build_mitunet_provenance,
    _prepare_mitunet_wall_mask_for_regions,
)

__all__ = [
    "MITUNET_BACKEND",
    "MITUNET_MASK_REGIONS_DXF_MODE",
    "MAX_MITUNET_REGION_WALL_THICKNESS",
    "MITUNET_MODEL_NAME",
    "mitunet_available",
    "infer_mitunet",
    "build_mitunet_region_plan",
    "align_opening_annotations_to_walls",
    "regions_to_wall_annotations",
    "generate_mitunet_region_dxf",
    "build_mitunet_provenance",
    "_prepare_mitunet_wall_mask_for_regions",
]
