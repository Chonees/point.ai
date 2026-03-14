from __future__ import annotations

from training.inspect_floorplancad_svg import extract_svg_semantics


def test_extract_svg_semantics_collects_layers_and_ids():
    svg = """<?xml version="1.0" encoding="utf-8"?>
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" viewBox="0 0 100 100">
      <g inkscape:label="layer0">
        <path semantic-id="33" stroke="rgb(178,0,178)" d="M 0,0 L 10,10" />
        <circle stroke="rgb(178,0,0)" cx="4" cy="4" r="1" />
      </g>
      <g inkscape:label="layerAXIS">
        <path semantic-id="12" stroke="rgb(92,92,92)" d="M 0,0 L 5,5" />
      </g>
    </svg>
    """

    semantics = extract_svg_semantics(svg)

    assert semantics["view_box"] == "0 0 100 100"
    assert semantics["layers"]["layer0"] == 1
    assert semantics["layers"]["layerAXIS"] == 1
    assert semantics["semantic_ids"]["33"] == 1
    assert semantics["semantic_ids"]["12"] == 1
    assert semantics["stroke_colors"]["rgb(178,0,178)"] == 1
    assert semantics["element_tags"]["path"] == 2
