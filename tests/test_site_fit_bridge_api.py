from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)


def test_bridge_propose_returns_cad_review_site_constraints_and_baseline_candidate(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-dimensions.dxf"
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        response = client.post(
            "/api/v2/site-fit/bridge/propose",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pipeline"] == "site_fit_bridge_mvp_v1"
    assert payload["scope"] == "seminole-2000-only"
    assert payload["plan_id"] == "seminole-2000"
    assert payload["proposal"]["status"] == "fit_ready"
    assert payload["proposal"]["candidates"][0]["candidate_id"] == "baseline_preserved"
    assert payload["site_constraints"]["placed_plan_footprint"]["width"] == 468.0
    assert payload["cad_analysis"]["fit_summary"]["buildable_polygon"]


def test_bridge_apply_reuses_site_constraints_and_applies_selected_candidate(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-dimensions.dxf"
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        propose_response = client.post(
            "/api/v2/site-fit/bridge/propose",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert propose_response.status_code == 200, propose_response.text
    proposal = propose_response.json()
    apply_response = client.post(
        "/api/v2/site-fit/bridge/apply",
        json={
            "plan_id": proposal["plan_id"],
            "site_constraints": proposal["site_constraints"],
            "candidate_id": proposal["proposal"]["candidates"][0]["candidate_id"],
            "cad_analysis_id": proposal["cad_analysis"]["analysis_id"],
        },
    )

    assert apply_response.status_code == 200, apply_response.text
    payload = apply_response.json()
    assert payload["pipeline"] == "site_fit_bridge_mvp_v1"
    assert payload["apply_id"]
    assert payload["export_url"] == f'/api/v2/site-fit/bridge/export/{payload["apply_id"]}'
    assert payload["apply"]["apply_status"] == "applied"
    assert payload["apply"]["candidate_id"] == "baseline_preserved"
    assert payload["apply"]["compliance_summary"]["status"] == "pass"


def test_bridge_export_returns_applied_dxf_using_registered_plan_dimensions(tmp_path: Path):
    dxf_path = tmp_path / "cad-sheet-dimensions.dxf"
    _write_dimensioned_sheet_dxf(dxf_path)

    with dxf_path.open("rb") as handle:
        propose_response = client.post(
            "/api/v2/site-fit/bridge/propose",
            files={"file": (dxf_path.name, handle, "application/dxf")},
        )

    assert propose_response.status_code == 200, propose_response.text
    proposal = propose_response.json()

    apply_response = client.post(
        "/api/v2/site-fit/bridge/apply",
        json={
            "plan_id": proposal["plan_id"],
            "site_constraints": proposal["site_constraints"],
            "candidate_id": proposal["proposal"]["candidates"][0]["candidate_id"],
            "cad_analysis_id": proposal["cad_analysis"]["analysis_id"],
        },
    )

    assert apply_response.status_code == 200, apply_response.text
    apply_payload = apply_response.json()

    export_response = client.get(apply_payload["export_url"])

    assert export_response.status_code == 200, export_response.text
    assert export_response.headers["content-type"].startswith("application/dxf")
    assert f'{apply_payload["apply_id"]}-bridge-apply.dxf' in export_response.headers["content-disposition"]

    exported_path = tmp_path / "bridge-apply-export.dxf"
    exported_path.write_bytes(export_response.content)
    exported = ezdxf.readfile(exported_path)
    assert exported.units == 1  # inches

    msp = exported.modelspace()
    layers = {entity.dxf.layer for entity in msp}
    assert {"PROP", "SETBACKS"} <= layers

    dimensions = sorted(str(entity.dxf.text) for entity in msp if entity.dxftype() == "DIMENSION")
    assert 'Footprint 39\'-0" | 468 in' in dimensions
    assert 'Footprint 66\'-0" | 792 in' in dimensions
    assert 'Footprint 100\'-0" | 1200 in' not in dimensions
    assert 'Footprint 200\'-0" | 2400 in' not in dimensions


def _write_dimensioned_sheet_dxf(path: Path) -> None:
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

    msp.add_lwpolyline([(250, 0), (340, 0), (340, 120), (250, 120)], close=True, dxfattribs={"layer": "PROP"})
    msp.add_lwpolyline([(265, 15), (325, 15), (325, 105), (265, 105)], close=True, dxfattribs={"layer": "SETBACKS"})
    msp.add_text("SITE PLAN", dxfattribs={"layer": "TEXT", "insert": (270, 132), "height": 3})
    msp.add_text("90.00", dxfattribs={"layer": "TEXT", "insert": (285, 138), "height": 3})

    doc.saveas(path)
