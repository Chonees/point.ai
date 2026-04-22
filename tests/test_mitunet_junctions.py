from backend.mitunet.junctions import resolve_wall_junctions


def test_resolve_wall_junctions_dxf_preserves_original_span_when_trims_cross():
    walls = [
        {
            "orientation": "vertical",
            "mid": 100.0,
            "span_lo": 10.0,
            "span_hi": 18.0,
            "half_lw": 2.0,
        },
        {
            "orientation": "horizontal",
            "mid": 12.0,
            "span_lo": 95.0,
            "span_hi": 105.0,
            "half_lw": 3.0,
        },
        {
            "orientation": "horizontal",
            "mid": 16.0,
            "span_lo": 95.0,
            "span_hi": 105.0,
            "half_lw": 3.0,
        },
    ]

    resolved = resolve_wall_junctions(walls, mode="dxf")

    assert resolved[0]["span_lo"] == 10.0
    assert resolved[0]["span_hi"] == 18.0
