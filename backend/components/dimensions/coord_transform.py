from __future__ import annotations


# These are PIXEL sizes matching the frontend 2D editor (renderCanvas.ts).
# They get multiplied by t_scale to produce DXF units, guaranteeing the
# DXF looks proportionally identical to the 2D editor.
DIM_TEXT_HEIGHT_PX = 14    # _renderDimension: fontSize = 14
DIM_DOT_SIZE_PX = 8
ROOM_NAME_HEIGHT_PX = 32   # renderCanvas label: nameSize = 32 * labelScale
ROOM_DIM_HEIGHT_PX = 22    # renderCanvas label: sqftSize = 22 * labelScale
FIRST_CHAIN_OFFSET = 8.0

# Legacy aliases kept for any external code that imports the old names
DIM_TEXT_HEIGHT = DIM_TEXT_HEIGHT_PX
ROOM_NAME_HEIGHT = ROOM_NAME_HEIGHT_PX
ROOM_DIM_HEIGHT = ROOM_DIM_HEIGHT_PX


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


def setup_dim_style(doc, dimlfac: float, plan_width_dxf: float = 1490.0, *, t_scale: float = 0.0) -> str:
    """Create a dimension style that mirrors the 2D editor text sizes.

    When ``t_scale`` is provided, text heights are computed from the pixel
    sizes used in the frontend renderer (renderCanvas.ts) multiplied by
    ``t_scale`` — guaranteeing the DXF is a proportional 1:1 match.
    Falls back to a plan-width ratio when t_scale is unknown.
    """
    name = "POINTAI_DIMS"
    if name in doc.dimstyles:
        doc.dimstyles.remove(name)
    _ensure_dot_block(doc)
    ds = doc.dimstyles.new(name)

    if t_scale > 0.001:
        text_h = DIM_TEXT_HEIGHT_PX * t_scale
        dot_sz = DIM_DOT_SIZE_PX * t_scale
    else:
        text_h = plan_width_dxf * (DIM_TEXT_HEIGHT_PX / 800.0)
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
