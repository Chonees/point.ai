from pathlib import Path

import ezdxf

from backend.floor_plan_catalog.audit import audit_floor_plan_source


def test_audit_floor_plan_source_collects_layers_blocks_and_room_labels(tmp_path: Path):
    dxf_path = tmp_path / "sample-floor.dxf"
    write_sample_floor_plan_dxf(dxf_path)

    audit = audit_floor_plan_source(dxf_path)

    assert "WALLS" in audit.source_layers
    assert "ROOM LBLS" in audit.source_layers
    assert audit.block_refs["TOILET1"] == 1
    assert "KITCHEN" in audit.room_labels


def write_sample_floor_plan_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)
    doc.units = 1
    msp = doc.modelspace()

    msp.add_line((0, 0), (120, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((120, 0), (120, 144), dxfattribs={"layer": "WALLS"})
    msp.add_text(
        "KITCHEN",
        dxfattribs={"layer": "ROOM LBLS", "height": 12, "insert": (60, 72)},
    )

    if "TOILET1" not in doc.blocks:
        block = doc.blocks.new(name="TOILET1")
        block.add_circle((0, 0), radius=6)
    msp.add_blockref("TOILET1", (20, 20), dxfattribs={"layer": "FIXTURES"})

    doc.saveas(path)
