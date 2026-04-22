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
        footprint_bbox={"width": 468.0, "height": 792.0},
        rooms=[],
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


def test_curate_floor_plan_seed_merges_extraction_and_audit(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="seminole-2000", name="SEMINOLE2000")

    assert seed.floor_plan_id == "seminole-2000"
    assert seed.footprint_bbox.width == 468.0
    assert len(seed.rooms) == 2
    assert seed.rooms[0].name == "BEDROOM 2"
    assert "WALLS" in seed.source_layers
    assert seed.readiness.status == "ready_for_catalog"


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
                        "width": 1633.66,
                        "height": 1080.0,
                        "area": 1666626.68,
                        "measurement_source": "room_region",
                    },
                    {
                        "name": "PORCH",
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
