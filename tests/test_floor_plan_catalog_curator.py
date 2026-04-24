import json
from subprocess import run
from pathlib import Path

import ezdxf

from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed
from backend.floor_plan_catalog.curator import curate_floor_plan_seed


def test_floor_plan_catalog_seed_exposes_minimum_curated_shape():
    seed = FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox={
            "x1": 0.0,
            "y1": 0.0,
            "x2": 468.0,
            "y2": 792.0,
            "width": 468.0,
            "height": 792.0,
        },
        rooms=[],
        cad_traces=[],
        source_layers=[],
        block_refs=[],
        readiness={
            "status": "ready_for_catalog",
            "issues": [],
        },
    )

    payload = seed.model_dump()

    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["canonical_unit"] == "inch"
    assert payload["readiness"]["status"] == "ready_for_catalog"
    assert payload["footprint_bbox"]["x2"] == 468.0


def test_curate_floor_plan_seed_merges_extraction_and_audit(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="seminole-2000", name="SEMINOLE2000")

    assert seed.floor_plan_id == "seminole-2000"
    assert seed.footprint_bbox.width == 468.0
    assert len(seed.rooms) == 2
    assert seed.rooms[0].name == "BEDROOM 2"
    assert seed.rooms[0].bbox.x1 == 0.0
    assert seed.rooms[0].bbox.y2 == 144.0
    assert seed.rooms[0].centroid.x == 60.0
    assert seed.rooms[0].centroid.y == 72.0
    assert len(seed.rooms[0].polygon) >= 4
    assert "WALLS" in seed.source_layers
    assert seed.readiness.status == "ready_for_catalog"
    assert seed.cad_traces
    assert seed.wall_traces
    assert any(trace.trace_kind == "door" for trace in seed.cad_traces)
    assert any(trace.trace_kind == "window" for trace in seed.cad_traces)
    assert seed.wall_traces[0].layer == "WALLS"
    assert seed.wall_traces[0].trace_id
    assert len({trace.trace_id for trace in seed.cad_traces}) == len(seed.cad_traces)


def test_curate_floor_plan_seed_marks_low_room_coverage_as_manual_review(tmp_path: Path):
    dxf_path = tmp_path / "weak-floor.dxf"
    write_sparse_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="santa-barbara", name="SANTA-BARBARA")

    assert seed.readiness.status == "needs_manual_review"
    assert "Room coverage is too low for a trusted catalog entry." in seed.readiness.issues


def test_curate_floor_plan_catalog_cli_writes_seed_json(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)
    output_path = tmp_path / "seminole-2000.json"

    result = run(
        [
            "C:\\Users\\lucas\\OneDrive\\Escritorio\\Point.ai\\.venv\\Scripts\\python.exe",
            "scripts/curate_floor_plan_catalog.py",
            str(dxf_path),
            "--floor-plan-id",
            "seminole-2000",
            "--name",
            "SEMINOLE2000",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["readiness"]["status"] == "ready_for_catalog"


def test_curate_floor_plan_seed_marks_aggregate_room_name_as_manual_review(monkeypatch, tmp_path: Path):
    dxf_path = tmp_path / "aggregate-floor.dxf"
    dxf_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "backend.floor_plan_catalog.curator.extract_cad_file",
        lambda path, source_name=None: {
            "canonical_unit": "inch",
            "warnings": [],
            "floor_plan": {
                "bbox": {"width": 1633.66, "height": 1080.0},
                    "rooms": [
                        {
                            "name": "COV'D. PATIO PANTRY MASTER BEDROOM DINING KITCHEN UTILITY MSTR. BATH LIVING ROOM BATH 2 BEDROOM 2 ENTRY BEDROOM 3",
                            "polygon": [],
                            "bbox": {"x1": 0.0, "y1": 0.0, "x2": 1633.66, "y2": 1080.0, "width": 1633.66, "height": 1080.0},
                            "centroid": {"x": 800.0, "y": 540.0},
                            "width": 1633.66,
                            "height": 1080.0,
                            "area": 1666626.68,
                            "measurement_source": "room_region",
                        },
                        {
                            "name": "PORCH",
                            "polygon": [],
                            "bbox": {"x1": 10.0, "y1": 10.0, "x2": 146.0, "y2": 190.0, "width": 136.0, "height": 180.0},
                            "centroid": {"x": 78.0, "y": 100.0},
                            "width": 136.0,
                            "height": 180.0,
                            "area": 11971.98,
                            "measurement_source": "room_region",
                        },
                ],
            },
        },
    )
    monkeypatch.setattr(
        "backend.floor_plan_catalog.curator.audit_floor_plan_source",
        lambda path: type(
            "Audit",
            (),
            {"source_layers": ["WALLS", "ROOM LBLS"], "block_refs": {"TOILET1": 2}},
        )(),
    )

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="santa-barbara", name="SANTA-BARBARA")

    assert seed.readiness.status == "needs_manual_review"
    assert "Aggregate room labels suggest unresolved room segmentation." in seed.readiness.issues


def write_dimensioned_room_floor_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)
    doc.units = 1
    msp = doc.modelspace()

    msp.add_lwpolyline(
        [(0, 0), (468, 0), (468, 792), (0, 792), (0, 0)],
        dxfattribs={"layer": "WALLS"},
    )
    msp.add_line((120, 0), (120, 144), dxfattribs={"layer": "WALLS"})
    msp.add_line((120, 144), (120, 288), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 144), (468, 144), dxfattribs={"layer": "WALLS"})
    msp.add_line((120, 52), (120, 96), dxfattribs={"layer": "DOORS"})
    msp.add_line((210, 0), (270, 0), dxfattribs={"layer": "WINS"})

    msp.add_text(
        "BEDROOM 2",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (60, 72)},
    )
    msp.add_text(
        "LIVING ROOM",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (240, 72)},
    )

    msp.add_text(
        '39\'-0"',
        dxfattribs={"layer": "DIMS", "height": 12, "insert": (234, -24)},
    )
    msp.add_text(
        '66\'-0"',
        dxfattribs={"layer": "DIMS", "height": 12, "insert": (-36, 396)},
    )

    doc.saveas(path)


def write_sparse_room_floor_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)
    doc.units = 1
    msp = doc.modelspace()

    msp.add_lwpolyline(
        [(0, 0), (300, 0), (300, 300), (0, 300), (0, 0)],
        dxfattribs={"layer": "WALLS"},
    )
    msp.add_text(
        "GARAGE",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (150, 150)},
    )

    doc.saveas(path)



def test_curate_floor_plan_seed_preserves_wall_trace_geometry(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path)
    polyline_trace = next(trace for trace in seed.wall_traces if trace.type == "polyline")
    line_trace = next(trace for trace in seed.wall_traces if trace.type == "line")

    assert len(polyline_trace.points) >= 4
    assert polyline_trace.bbox.width == 468.0
    assert line_trace.start is not None
    assert line_trace.end is not None


def test_curate_floor_plan_seed_separates_opening_trace_kinds(tmp_path: Path):
    dxf_path = tmp_path / "opening-aware-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path)
    trace_kinds = {trace.trace_kind for trace in seed.cad_traces}
    door_traces = [trace for trace in seed.cad_traces if trace.trace_kind == "door"]
    window_traces = [trace for trace in seed.cad_traces if trace.trace_kind == "window"]

    assert {"wall", "door", "window"}.issubset(trace_kinds)
    assert door_traces
    assert window_traces
    assert all(trace.layer == "DOORS" for trace in door_traces)
    assert all(trace.layer in {"WIN", "WINS"} for trace in window_traces)


def test_curate_floor_plan_seed_makes_duplicate_wall_trace_ids_unique(tmp_path: Path):
    dxf_path = tmp_path / "duplicate-wall-floor.dxf"
    write_duplicate_wall_trace_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path)
    trace_ids = [trace.trace_id for trace in seed.wall_traces]

    assert len(trace_ids) >= 2
    assert len(set(trace_ids)) == len(trace_ids)


def write_duplicate_wall_trace_floor_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)
    doc.units = 1
    msp = doc.modelspace()

    msp.add_line((0, 0), (120, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 0), (120, 0), dxfattribs={"layer": "WALLS"})
    msp.add_text(
        "GARAGE",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (60, 30)},
    )
    msp.add_text(
        "UTILITY",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (60, 80)},
    )

    doc.saveas(path)
