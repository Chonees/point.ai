from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from backend.app import app


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
