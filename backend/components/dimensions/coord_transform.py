from __future__ import annotations


DIM_TEXT_HEIGHT = 3.5
DIM_DOT_SIZE = 3.5
ROOM_NAME_HEIGHT = 7.4
ROOM_DIM_HEIGHT = 3.5
FIRST_CHAIN_OFFSET = 8.0


class CoordTransform:
    def __init__(self, image_shape: tuple[int, int], transform: dict, scale_ipp: float):
        self.h, self.w = image_shape
        self.t_scale = float(transform.get("scale", 1.0) or 1.0)
        self.t_ox = float(transform.get("offset_x", 0.0) or 0.0)
        self.t_oy = float(transform.get("offset_y", 0.0) or 0.0)
        self.scale_ipp = float(scale_ipp)

    def to_dxf(self, ix: float, iy: float) -> tuple[float, float]:
        dx = ix * self.t_scale + self.t_ox
        dy = (self.h - iy) * self.t_scale + self.t_oy
        return dx, dy

    @property
    def dimlfac(self) -> float:
        if self.t_scale < 0.001:
            return 1.0
        return self.scale_ipp / self.t_scale


def _ensure_dot_block(doc):
    if "_DOT" in doc.blocks:
        return
    blk = doc.blocks.new(name="_DOT")
    blk.add_lwpolyline([(-0.5, 0, 1.0), (0.5, 0, 1.0)], format="xyb", close=True)


def setup_dim_style(doc, dimlfac: float, plan_width_dxf: float = 1490.0) -> str:
    """Create a dimension style that matches the Seminole visual ratio."""
    name = "POINTAI_DIMS"
    if name in doc.dimstyles:
        doc.dimstyles.remove(name)
    _ensure_dot_block(doc)
    ds = doc.dimstyles.new(name)

    visual_ratio = 3.5 / 1300.0
    text_h = plan_width_dxf * visual_ratio
    dot_sz = text_h
    gap = text_h * 0.4

    ds.dxf.dimlfac = dimlfac
    ds.dxf.dimtxt = text_h
    ds.dxf.dimasz = dot_sz
    ds.dxf.dimgap = gap
    ds.dxf.dimexo = text_h * 0.15
    ds.dxf.dimexe = text_h * 0.15
    ds.dxf.dimdle = 0
    ds.dxf.dimtad = 1
    ds.dxf.dimjust = 0
    ds.dxf.dimtsz = 0
    ds.dxf.dimblk = "_DOT"
    ds.dxf.dimblk1 = "_DOT"
    ds.dxf.dimblk2 = "_DOT"
    ds.dxf.dimlunit = 4
    ds.dxf.dimdec = 0
    ds.dxf.dimzin = 0
    ds.dxf.dimclrd = 0
    ds.dxf.dimclre = 0
    ds.dxf.dimclrt = 0
    return name


def _ensure_layers(doc):
    for name, color in [("DIMS", 137), ("ROOM LBLS", 253)]:
        if name not in doc.layers:
            doc.layers.add(name, color=color)
