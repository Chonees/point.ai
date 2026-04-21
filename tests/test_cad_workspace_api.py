from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from backend.app import app
from backend.cad_workspace.extractor import ExtractedCadEntity, _extract_rasterized_rooms


client = TestClient(app)


def test_cad_workspace_extract_separates_floor_and_site_views(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet.dxf"
    _write_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_name"] == "cad-sheet.dxf"
    assert payload["source_format"] == "dxf"
    assert payload["canonical_unit"] == "inch"
    assert payload["floor_plan"]["role"] == "floor_plan"
    assert payload["site_plan"]["role"] == "site_plan"
    assert payload["floor_plan"]["bbox"]["width"] == 600.0
    assert payload["site_plan"]["bbox"]["width"] == 480.0
    assert payload["floor_plan"]["summary"]["text_count"] == 0
    assert payload["site_plan"]["summary"]["text_count"] == 0
    assert payload["floor_plan"]["summary"]["entity_count"] > payload["site_plan"]["summary"]["entity_count"]
    assert payload["side_by_side"]["canonical_unit"] == "inch"
    assert payload["fit_summary"]["fits_within_buildable_bbox"] is None


def test_cad_workspace_extract_normalizes_floor_walls_from_dimensions(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-dimensions.dxf"
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["floor_plan"]["measurements"]["source"] == "dimensions"
    assert payload["floor_plan"]["bbox"]["width"] == 468.0
    assert payload["floor_plan"]["bbox"]["height"] == 792.0
    assert {entity["layer"] for entity in payload["floor_plan"]["entities"]} == {"WALLS"}
    assert payload["site_plan"]["summary"]["text_count"] == 0
    assert {entity["layer"] for entity in payload["site_plan"]["entities"]} == {"PROP", "SETBACKS"}
    assert payload["fit_summary"]["basis"] == "buildable_polygon"
    assert payload["fit_summary"]["buildable_bbox"]["width"] == 720.0
    assert payload["fit_summary"]["buildable_bbox"]["height"] == 1080.0
    assert len(payload["fit_summary"]["buildable_polygon"]) >= 4
    assert payload["fit_summary"]["width_delta"] == 252.0
    assert payload["fit_summary"]["height_delta"] == 288.0
    assert payload["fit_summary"]["fits_within_buildable_polygon"] is True
    assert payload["fit_summary"]["fits_within_buildable_bbox"] is True


def test_cad_workspace_extract_rejects_non_cad_files():
    response = client.post(
        "/api/cad-workspace/extract",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 422, response.text
    assert "Only .dxf and .dwg files are supported." in response.json()["detail"]


def test_cad_workspace_export_overlay_returns_downloadable_dxf(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-dimensions.dxf"
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        extract_response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert extract_response.status_code == 200, extract_response.text
    analysis_id = extract_response.json()["analysis_id"]

    export_response = client.get(f"/api/cad-workspace/export-overlay/{analysis_id}")

    assert export_response.status_code == 200, export_response.text
    assert export_response.headers["content-type"].startswith("application/dxf")
    assert f'{analysis_id}-overlay.dxf' in export_response.headers["content-disposition"]

    exported_path = tmp_path / "overlay-export.dxf"
    exported_path.write_bytes(export_response.content)
    exported = ezdxf.readfile(exported_path)
    assert exported.units == 1  # inches

    msp = exported.modelspace()
    floor_lines = [entity for entity in msp if entity.dxftype() == "LINE" and entity.dxf.layer == "FLOOR_OVERLAY"]
    assert len(floor_lines) == 4

    xs = [float(line.dxf.start.x) for line in floor_lines] + [float(line.dxf.end.x) for line in floor_lines]
    ys = [float(line.dxf.start.y) for line in floor_lines] + [float(line.dxf.end.y) for line in floor_lines]
    assert min(xs) == 306.0
    assert max(xs) == 774.0
    assert min(ys) == 324.0
    assert max(ys) == 1116.0

    dimensions = [entity for entity in msp if entity.dxftype() == "DIMENSION"]
    assert len(dimensions) == 4
    dimension_texts = sorted(str(entity.dxf.text) for entity in dimensions)
    assert dimension_texts == [
        'Buildable 60\'-0" | 720 in',
        'Buildable 90\'-0" | 1080 in',
        'Footprint 39\'-0" | 468 in',
        'Footprint 66\'-0" | 792 in',
    ]


def test_cad_workspace_polygon_fit_rejects_tapered_buildable_even_if_bbox_is_large_enough(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-tapered.dxf"
    _write_tapered_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fit_summary"]["basis"] == "buildable_polygon"
    assert payload["fit_summary"]["fits_within_buildable_bbox"] is True
    assert payload["fit_summary"]["fits_within_buildable_polygon"] is False


def test_cad_workspace_extracts_floor_rooms_and_measurements(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-rooms.dxf"
    _write_room_labeled_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    rooms = payload["floor_plan"]["rooms"]
    assert len(rooms) == 2
    assert [room["name"] for room in rooms] == ["BEDROOM 2", "LIVING ROOM"]
    assert rooms[0]["width"] == 120.0
    assert rooms[0]["height"] == 144.0
    assert rooms[1]["width"] == 240.0
    assert rooms[1]["height"] == 144.0
    assert rooms[0]["measurement_source"] == "room_region"
    assert rooms[1]["measurement_source"] == "room_region"


def test_cad_workspace_extracts_site_from_single_spatial_cluster_when_layers_are_clear(tmp_path: Path):
    dxf_path = tmp_path / "cad-single-cluster.dxf"
    _write_single_cluster_mixed_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["floor_plan"]["bbox"]["width"] == 468.0
    assert payload["floor_plan"]["bbox"]["height"] == 792.0
    assert {entity["layer"] for entity in payload["site_plan"]["entities"]} == {"PROP", "SETBACKS"}
    assert payload["site_plan"]["bbox"]["width"] == 1080.0
    assert payload["site_plan"]["bbox"]["height"] == 1620.0
    assert payload["fit_summary"]["buildable_bbox"]["width"] == 900.0
    assert payload["fit_summary"]["buildable_bbox"]["height"] == 1440.0
    assert payload["fit_summary"]["basis"] == "buildable_polygon"
    assert any("separated by cad layers" in warning.lower() for warning in payload["warnings"])
    assert not any("site extraction may be incomplete" in warning.lower() for warning in payload["warnings"])


def test_cad_workspace_floor_fallback_excludes_site_layers_when_floor_layer_is_generic(tmp_path: Path):
    dxf_path = tmp_path / "cad-single-cluster-generic-floor.dxf"
    _write_single_cluster_generic_floor_layer_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert {entity["layer"] for entity in payload["floor_plan"]["entities"]} == {"PLAN"}
    assert payload["floor_plan"]["bbox"]["width"] == 468.0
    assert payload["floor_plan"]["bbox"]["height"] == 792.0
    assert {entity["layer"] for entity in payload["site_plan"]["entities"]} == {"PROP", "SETBACKS"}
    assert payload["fit_summary"]["footprint_bbox"]["width"] == 468.0
    assert payload["fit_summary"]["footprint_bbox"]["height"] == 792.0


def test_cad_workspace_floor_fallback_ignores_dimension_entities_when_floor_layer_is_generic(tmp_path: Path):
    dxf_path = tmp_path / "cad-generic-floor-with-dimension-entities.dxf"
    _write_generic_floor_with_dimension_entities_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/cad-workspace/extract",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert {entity["layer"] for entity in payload["floor_plan"]["entities"]} == {"PLAN"}
    assert payload["floor_plan"]["bbox"]["width"] == 1200.0
    assert payload["floor_plan"]["bbox"]["height"] == 2400.0


def test_rasterized_room_fallback_builds_region_polygon_instead_of_raw_bbox():
    geometry = [
        _line_entity("WALLS", (0, 0), (240, 0)),
        _line_entity("WALLS", (240, 0), (240, 240)),
        _line_entity("WALLS", (240, 240), (0, 240)),
        _line_entity("WALLS", (0, 240), (0, 0)),
        _line_entity("WALLS", (144, 168), (144, 240)),
        _line_entity("WALLS", (168, 144), (240, 144)),
        _line_entity("DOORS", (144, 144), (144, 168)),
        _line_entity("DOORS", (144, 144), (168, 144)),
    ]
    labels = [_text_entity("ROOM LBLS", "LIVING ROOM", (96, 96))]

    rooms = _extract_rasterized_rooms(geometry, labels)

    assert len(rooms) == 1
    room = rooms[0]
    assert room.measurement_source == "label_region_fill"
    assert room.area < 54000.0
    assert len(room.polygon) > 5


def test_rasterized_room_fallback_splits_open_component_by_multiple_room_labels():
    geometry = [
        _line_entity("WALLS", (0, 0), (240, 0)),
        _line_entity("WALLS", (240, 0), (240, 144)),
        _line_entity("WALLS", (240, 144), (0, 144)),
        _line_entity("WALLS", (0, 144), (0, 0)),
    ]
    labels = [
        _text_entity("ROOM LBLS", "KITCHEN", (60, 72)),
        _text_entity("ROOM LBLS", "LIVING ROOM", (180, 72)),
    ]

    rooms = _extract_rasterized_rooms(geometry, labels)

    assert len(rooms) == 2
    assert [room.name for room in rooms] == ["KITCHEN", "LIVING ROOM"]


def _write_sheet_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    # Floor plan cluster (largest)
    msp.add_line((0, 0), (50, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((50, 0), (50, 24), dxfattribs={"layer": "A-WALL"})
    msp.add_line((50, 24), (0, 24), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 24), (0, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (8, 26), "height": 1})

    # Site plan cluster 1
    msp.add_lwpolyline([(200, 0), (240, 0), (240, 20), (200, 20)], close=True, dxfattribs={"layer": "SITE"})
    msp.add_text("LOT", dxfattribs={"layer": "TEXT", "insert": (210, 22), "height": 1})

    # Site plan cluster 2 (still part of the site side)
    msp.add_lwpolyline([(200, 40), (230, 40), (230, 60), (200, 60)], close=True, dxfattribs={"layer": "SITE"})
    msp.add_text("BUILDABLE", dxfattribs={"layer": "TEXT", "insert": (202, 63), "height": 1})

    doc.saveas(path)


def _line_entity(layer: str, start: tuple[float, float], end: tuple[float, float]) -> ExtractedCadEntity:
    x1, y1 = start
    x2, y2 = end
    return ExtractedCadEntity(
        type="line",
        layer=layer,
        start={"x": float(x1), "y": float(y1)},
        end={"x": float(x2), "y": float(y2)},
        bbox={
            "x1": float(min(x1, x2)),
            "y1": float(min(y1, y2)),
            "x2": float(max(x1, x2)),
            "y2": float(max(y1, y2)),
            "width": float(abs(x2 - x1)),
            "height": float(abs(y2 - y1)),
        },
    )


def _text_entity(layer: str, text: str, position: tuple[float, float]) -> ExtractedCadEntity:
    x, y = position
    return ExtractedCadEntity(
        type="text",
        layer=layer,
        text=text,
        position={"x": float(x), "y": float(y)},
        bbox={
            "x1": float(x),
            "y1": float(y),
            "x2": float(x),
            "y2": float(y),
            "width": 0.0,
            "height": 0.0,
        },
    )


def _write_dimensioned_sheet_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    # Floor-plan sheet view: oversized raw geometry but real dimensions on DIMS.
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 0), (100, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 200), (0, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 200), (0, 0), dxfattribs={"layer": "WALLS"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (20, 220), "height": 3})
    msp.add_text('\\A1;39\'-0"', dxfattribs={"layer": "DIMS", "insert": (35, 230), "height": 3})
    msp.add_text('\\A1;66\'-0"', dxfattribs={"layer": "DIMS", "insert": (-15, 110), "height": 3})

    # Site-plan sheet view: only property + setbacks should survive.
    msp.add_lwpolyline([(250, 0), (340, 0), (340, 120), (250, 120)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(265, 15), (325, 15), (325, 105), (265, 105)], close=True, dxfattribs={"layer": "SETBACKS"})
    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (270, 132), "height": 3})
    msp.add_text("90.00", dxfattribs={"layer": "TEXT", "insert": (285, 138), "height": 3})

    doc.saveas(path)


def _write_tapered_sheet_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 0), (100, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 200), (0, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 200), (0, 0), dxfattribs={"layer": "WALLS"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (20, 220), "height": 3})
    msp.add_text('\\A1;39\'-0"', dxfattribs={"layer": "DIMS", "insert": (35, 230), "height": 3})
    msp.add_text('\\A1;66\'-0"', dxfattribs={"layer": "DIMS", "insert": (-15, 110), "height": 3})

    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (270, 132), "height": 3})
    msp.add_lwpolyline([(250, 0), (360, 0), (340, 140), (230, 140)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(290, 15), (300, 15), (340, 120), (250, 120)], close=True, dxfattribs={"layer": "SETBACKS"})

    doc.saveas(path)


def _write_room_labeled_sheet_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    # 30' x 12' floor split into 10' bedroom + 20' living room
    msp.add_line((0, 0), (30, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((30, 0), (30, 12), dxfattribs={"layer": "WALLS"})
    msp.add_line((30, 12), (0, 12), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 12), (0, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((10, 0), (10, 12), dxfattribs={"layer": "WALLS"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (4, 15), "height": 1})
    msp.add_text("BEDROOM 2", dxfattribs={"layer": "ROOM LBLS", "insert": (5, 6), "height": 1})
    msp.add_text("LIVING ROOM", dxfattribs={"layer": "ROOM LBLS", "insert": (20, 6), "height": 1})
    msp.add_text('\\A1;30\'-0"', dxfattribs={"layer": "DIMS", "insert": (15, 16), "height": 1})
    msp.add_text('\\A1;12\'-0"', dxfattribs={"layer": "DIMS", "insert": (-2, 6), "height": 1})

    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (60, 14), "height": 1})
    msp.add_lwpolyline([(60, 0), (100, 0), (100, 30), (60, 30)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(65, 5), (95, 5), (95, 25), (65, 25)], close=True, dxfattribs={"layer": "SETBACKS"})

    doc.saveas(path)


def _write_single_cluster_mixed_sheet_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 0), (100, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((100, 200), (0, 200), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 200), (0, 0), dxfattribs={"layer": "WALLS"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (20, 220), "height": 3})
    msp.add_text('\\A1;39\'-0"', dxfattribs={"layer": "DIMS", "insert": (35, 230), "height": 3})
    msp.add_text('\\A1;66\'-0"', dxfattribs={"layer": "DIMS", "insert": (-15, 110), "height": 3})

    msp.add_lwpolyline([(140, 10), (230, 10), (230, 145), (140, 145)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(150, 20), (225, 20), (225, 140), (150, 140)], close=True, dxfattribs={"layer": "SETBACKS"})
    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (155, 154), "height": 3})
    msp.add_line((100, 72), (140, 72), dxfattribs={"layer": "TEXT"})

    doc.saveas(path)


def _write_single_cluster_generic_floor_layer_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PLAN"})
    msp.add_line((100, 0), (100, 200), dxfattribs={"layer": "PLAN"})
    msp.add_line((100, 200), (0, 200), dxfattribs={"layer": "PLAN"})
    msp.add_line((0, 200), (0, 0), dxfattribs={"layer": "PLAN"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (20, 220), "height": 3})
    msp.add_text('\\A1;39\'-0"', dxfattribs={"layer": "DIMS", "insert": (35, 230), "height": 3})
    msp.add_text('\\A1;66\'-0"', dxfattribs={"layer": "DIMS", "insert": (-15, 110), "height": 3})
    msp.add_text("BEDROOM 2", dxfattribs={"layer": "ROOM LBLS", "insert": (50, 100), "height": 3})

    msp.add_lwpolyline([(140, 10), (230, 10), (230, 145), (140, 145)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(150, 20), (225, 20), (225, 140), (150, 140)], close=True, dxfattribs={"layer": "SETBACKS"})
    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (155, 154), "height": 3})
    msp.add_line((100, 72), (140, 72), dxfattribs={"layer": "TEXT"})

    doc.saveas(path)


def _write_generic_floor_with_dimension_entities_dxf(path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = 2  # feet
    msp = doc.modelspace()

    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "PLAN"})
    msp.add_line((100, 0), (100, 200), dxfattribs={"layer": "PLAN"})
    msp.add_line((100, 200), (0, 200), dxfattribs={"layer": "PLAN"})
    msp.add_line((0, 200), (0, 0), dxfattribs={"layer": "PLAN"})
    msp.add_text("FLOOR PLAN", dxfattribs={"layer": "TEXT", "insert": (20, 220), "height": 3})

    horizontal = msp.add_linear_dim(base=(0, 220), p1=(0, 200), p2=(100, 200), angle=0, dxfattribs={"layer": "DIMS"})
    horizontal.render()
    vertical = msp.add_linear_dim(base=(-20, 0), p1=(0, 0), p2=(0, 200), angle=90, dxfattribs={"layer": "DIMS"})
    vertical.render()

    msp.add_lwpolyline([(140, 10), (230, 10), (230, 145), (140, 145)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(150, 20), (225, 20), (225, 140), (150, 140)], close=True, dxfattribs={"layer": "SETBACKS"})
    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (155, 154), "height": 3})

    doc.saveas(path)
