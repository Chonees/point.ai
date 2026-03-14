from backend.structure_postprocess import build_junction_graph, postprocess_structure


def _box_walls():
    """Simple box: 4 exterior walls forming a rectangle."""
    return [
        {
            "id": "w1", "orientation": "horizontal",
            "polyline": [{"x": 0, "y": 0}, {"x": 200, "y": 0}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": True, "side": "bottom",
        },
        {
            "id": "w2", "orientation": "horizontal",
            "polyline": [{"x": 0, "y": 120}, {"x": 200, "y": 120}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": True, "side": "top",
        },
        {
            "id": "w3", "orientation": "vertical",
            "polyline": [{"x": 0, "y": 0}, {"x": 0, "y": 120}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": True, "side": "left",
        },
        {
            "id": "w4", "orientation": "vertical",
            "polyline": [{"x": 200, "y": 0}, {"x": 200, "y": 120}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": True, "side": "right",
        },
    ]


def test_box_has_4_L_junctions():
    walls = _box_walls()
    junctions = build_junction_graph(walls)

    assert len(junctions) == 4
    assert all(j["type"] == "L" for j in junctions)


def test_T_junction_with_interior_wall():
    walls = _box_walls()
    # Add interior wall meeting the bottom wall
    walls.append({
        "id": "w5", "orientation": "vertical",
        "polyline": [{"x": 100, "y": 0}, {"x": 100, "y": 120}],
        "thickness": 4.0, "confidence": 0.8, "is_exterior": False, "side": None,
    })
    junctions = build_junction_graph(walls)

    types = {j["type"] for j in junctions}
    assert "T" in types
    # w5 touches w1 at endpoint (T: v-endpoint meets h-body at x=100)
    # w5 touches w2 at endpoint (T: v-endpoint meets h-body at x=100)
    t_junctions = [j for j in junctions if j["type"] == "T"]
    assert len(t_junctions) == 2


def test_X_junction_crossing_walls():
    walls = [
        {
            "id": "h1", "orientation": "horizontal",
            "polyline": [{"x": 0, "y": 50}, {"x": 200, "y": 50}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": False, "side": None,
        },
        {
            "id": "v1", "orientation": "vertical",
            "polyline": [{"x": 100, "y": 0}, {"x": 100, "y": 120}],
            "thickness": 4.0, "confidence": 0.9, "is_exterior": False, "side": None,
        },
    ]
    junctions = build_junction_graph(walls)

    assert len(junctions) == 1
    assert junctions[0]["type"] == "X"
    assert junctions[0]["point"] == {"x": 100.0, "y": 50.0}


def test_postprocess_includes_junction_metrics():
    walls = _box_walls()
    # Add raw-style walls (without side, will be classified by postprocess)
    raw_walls = []
    for w in walls:
        raw_walls.append({
            "id": w["id"],
            "orientation": w["orientation"],
            "polyline": w["polyline"],
            "thickness": w["thickness"],
            "confidence": w["confidence"],
            "is_exterior": False,
        })

    result = postprocess_structure(walls=raw_walls, openings=[])

    assert "junction_count" in result["metrics"]
    assert "junction_L" in result["metrics"]
    assert result["metrics"]["junction_count"] >= 4
    assert "junctions" in result
