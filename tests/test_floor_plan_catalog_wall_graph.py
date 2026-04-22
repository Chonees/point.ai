import json
from pathlib import Path

from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
    CatalogWallTrace,
    FloorPlanCatalogSeed,
)
from backend.floor_plan_catalog.topology import derive_floor_plan_topology
from backend.floor_plan_catalog.wall_graph import derive_floor_plan_wall_graph


def build_seed() -> FloorPlanCatalogSeed:
    return FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=240, y2=792, width=240, height=792),
        rooms=[
            CatalogRoom(
                name="KITCHEN",
                polygon=[
                    CatalogPoint(x=0, y=500),
                    CatalogPoint(x=160, y=500),
                    CatalogPoint(x=160, y=792),
                    CatalogPoint(x=0, y=792),
                ],
                bbox=CatalogBBox(x1=0, y1=500, x2=160, y2=792, width=160, height=292),
                centroid=CatalogPoint(x=80, y=646),
                width=160,
                height=292,
                area=46720,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="BEDROOM 2",
                polygon=[
                    CatalogPoint(x=0, y=300),
                    CatalogPoint(x=160, y=300),
                    CatalogPoint(x=160, y=500),
                    CatalogPoint(x=0, y=500),
                ],
                bbox=CatalogBBox(x1=0, y1=300, x2=160, y2=500, width=160, height=200),
                centroid=CatalogPoint(x=80, y=400),
                width=160,
                height=200,
                area=32000,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="HALL",
                polygon=[
                    CatalogPoint(x=160, y=300),
                    CatalogPoint(x=240, y=300),
                    CatalogPoint(x=240, y=500),
                    CatalogPoint(x=160, y=500),
                ],
                bbox=CatalogBBox(x1=160, y1=300, x2=240, y2=500, width=80, height=200),
                centroid=CatalogPoint(x=200, y=400),
                width=80,
                height=200,
                area=16000,
                measurement_source="room_region",
            ),
        ],
        wall_traces=[
            CatalogWallTrace(
                trace_id="trace-room-divider-horizontal",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=0, y=500),
                end=CatalogPoint(x=160, y=500),
                bbox=CatalogBBox(x1=0, y1=500, x2=160, y2=500, width=160, height=0),
            ),
            CatalogWallTrace(
                trace_id="trace-room-divider-vertical",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=160, y=300),
                end=CatalogPoint(x=160, y=500),
                bbox=CatalogBBox(x1=160, y1=300, x2=160, y2=500, width=0, height=200),
            ),
            CatalogWallTrace(
                trace_id="trace-hall-exterior",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=240, y=300),
                end=CatalogPoint(x=240, y=500),
                bbox=CatalogBBox(x1=240, y1=300, x2=240, y2=500, width=0, height=200),
            ),
        ],
        source_layers=["WALLS", "ROOM LBLS", "DOORS"],
        block_refs=["TOILET1"],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def build_multi_trace_inferred_seed() -> FloorPlanCatalogSeed:
    return FloorPlanCatalogSeed(
        floor_plan_id="multi-trace-inferred",
        name="MULTI TRACE INFERRED",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/MULTI.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=240, y2=220, width=240, height=220),
        rooms=[
            CatalogRoom(
                name="ROOM A",
                polygon=[
                    CatalogPoint(x=20, y=20),
                    CatalogPoint(x=120, y=20),
                    CatalogPoint(x=120, y=100),
                    CatalogPoint(x=20, y=100),
                ],
                bbox=CatalogBBox(x1=20, y1=20, x2=120, y2=100, width=100, height=80),
                centroid=CatalogPoint(x=70, y=60),
                width=100,
                height=80,
                area=8000,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="ROOM B",
                polygon=[
                    CatalogPoint(x=20, y=106),
                    CatalogPoint(x=120, y=106),
                    CatalogPoint(x=120, y=186),
                    CatalogPoint(x=20, y=186),
                ],
                bbox=CatalogBBox(x1=20, y1=106, x2=120, y2=186, width=100, height=80),
                centroid=CatalogPoint(x=70, y=146),
                width=100,
                height=80,
                area=8000,
                measurement_source="room_region",
            ),
        ],
        wall_traces=[
            CatalogWallTrace(
                trace_id="trace-a",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=20, y=103),
                end=CatalogPoint(x=60, y=103),
                bbox=CatalogBBox(x1=20, y1=103, x2=60, y2=103, width=40, height=0),
            ),
            CatalogWallTrace(
                trace_id="trace-b",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=70, y=103),
                end=CatalogPoint(x=120, y=103),
                bbox=CatalogBBox(x1=70, y1=103, x2=120, y2=103, width=50, height=0),
            ),
        ],
        source_layers=["WALLS", "ROOM LBLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def test_derive_floor_plan_wall_graph_creates_shared_and_exterior_boundaries():
    seed = build_seed()
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)
    walls = wall_graph.walls

    assert wall_graph.wall_graph_readiness.status == "ready_for_wall_graph_review"
    assert wall_graph.wall_graph_issues == []
    assert any(not wall.is_exterior for wall in walls)
    assert any(wall.is_exterior for wall in walls)

    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")
    hall = next(room for room in topology.rooms if room.name == "HALL")
    shared_wall = next(
        wall
        for wall in walls
        if not wall.is_exterior and set(wall.room_ids) == {bedroom.room_id, hall.room_id}
    )

    assert shared_wall.orientation == "vertical"
    assert shared_wall.length == 200
    assert shared_wall.start == CatalogPoint(x=160, y=300)
    assert shared_wall.end == CatalogPoint(x=160, y=500)
    assert shared_wall.trace_support_status == "exact_trace_supported"
    assert shared_wall.trace_support_ids == ["trace-room-divider-vertical"]
    assert shared_wall.trace_support_gap == 0.0

    hall_exterior = next(
        wall
        for wall in walls
        if wall.is_exterior and wall.room_ids == [hall.room_id] and wall.orientation == "vertical"
    )
    assert hall_exterior.start == CatalogPoint(x=240, y=300)
    assert hall_exterior.end == CatalogPoint(x=240, y=500)
    assert hall_exterior.trace_support_status == "exact_trace_supported"
    assert hall_exterior.trace_support_ids == ["trace-hall-exterior"]


def test_derive_floor_plan_wall_graph_falls_back_to_bbox_inference_when_polygons_do_not_touch():
    seed = build_seed().model_copy(deep=True)
    seed.rooms[0].polygon[0] = CatalogPoint(x=0, y=500.99)
    seed.rooms[0].polygon[1] = CatalogPoint(x=160, y=500.99)
    seed.rooms[0].bbox = CatalogBBox(x1=0, y1=500.99, x2=160, y2=792, width=160, height=291.01)

    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)

    kitchen = next(room for room in topology.rooms if room.name == "KITCHEN")
    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")
    inferred_wall = next(
        wall
        for wall in wall_graph.walls
        if set(wall.room_ids) == {kitchen.room_id, bedroom.room_id}
    )

    assert inferred_wall.orientation == "horizontal"
    assert inferred_wall.start == CatalogPoint(x=0, y=500)
    assert inferred_wall.end == CatalogPoint(x=160, y=500)
    assert inferred_wall.provenance == "bbox_inferred"
    assert inferred_wall.confidence == "trace_supported"
    assert inferred_wall.issues == []
    assert inferred_wall.trace_support_status == "snapped_to_trace"
    assert inferred_wall.trace_support_ids == ["trace-room-divider-horizontal"]
    assert inferred_wall.trace_support_gap == 0.495
    assert wall_graph.wall_graph_readiness.status == "ready_for_wall_graph_review"
    assert wall_graph.wall_graph_issues == []


def test_derive_floor_plan_wall_graph_deduplicates_shared_boundaries():
    seed = build_seed()
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)
    shared_pairs = [tuple(sorted(wall.room_ids)) for wall in wall_graph.walls if not wall.is_exterior]

    assert len(shared_pairs) == len(set(shared_pairs))


def test_derive_floor_plan_wall_graph_handles_real_seminole_seed():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)

    assert wall_graph.floor_plan_id == "seminole-2000"
    assert wall_graph.walls
    assert any(len(wall.room_ids) == 2 for wall in wall_graph.walls)
    assert any(wall.is_exterior for wall in wall_graph.walls)


def test_derive_floor_plan_wall_graph_merges_multi_trace_support_for_inferred_wall():
    seed = build_multi_trace_inferred_seed()
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)

    room_a = next(room for room in topology.rooms if room.name == "ROOM A")
    room_b = next(room for room in topology.rooms if room.name == "ROOM B")
    shared_wall = next(
        wall
        for wall in wall_graph.walls
        if not wall.is_exterior and set(wall.room_ids) == {room_a.room_id, room_b.room_id}
    )

    assert shared_wall.trace_support_status == "exact_trace_supported"
    assert shared_wall.trace_support_ids == ["trace-a", "trace-b"]
    assert shared_wall.start == CatalogPoint(x=20, y=103)
    assert shared_wall.end == CatalogPoint(x=120, y=103)
    assert shared_wall.trace_support_gap == 0.0
    assert shared_wall.provenance == "bbox_inferred"
    assert shared_wall.confidence == "exact"
    assert "inferred_from_bbox" not in shared_wall.issues


def test_derive_floor_plan_wall_graph_prunes_false_pairs_and_slivers_in_real_seminole():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology, seed.wall_traces)
    names_by_room_id = {room.room_id: room.name for room in topology.rooms}
    shared_pairs = {
        tuple(sorted(names_by_room_id[room_id] for room_id in wall.room_ids)): wall
        for wall in wall_graph.walls
        if not wall.is_exterior
    }

    assert ("BEDROOM 2", "KITCHEN") not in shared_pairs
    assert ("LIVING ROOM", "MSTR. BEDROOM") not in shared_pairs

    closet_wall = shared_pairs[tuple(sorted(("CLOSET", "MASTER BATH")))]
    assert closet_wall.trace_support_status == "snapped_to_trace"
    assert len(closet_wall.trace_support_ids) >= 2
    assert closet_wall.provenance == "bbox_inferred"
    assert closet_wall.confidence == "trace_supported"
    assert "inferred_from_bbox" not in closet_wall.issues
    assert wall_graph.wall_graph_issues == []



def test_export_topology_fixture_includes_wall_graph(tmp_path: Path):
    seed_path = tmp_path / "seminole-2000.json"
    output_path = tmp_path / "catalogInspector.fixture.json"
    seed = build_seed()
    seed_path.write_text(seed.model_dump_json(indent=2), encoding="utf-8")

    from scripts.export_seminole_topology_fixture import export_topology_fixture

    payload = export_topology_fixture(seed_path, output_path)

    assert output_path.exists()
    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["walls"]
    assert "trace_support_status" in payload["walls"][0]
    assert payload["wall_graph_readiness"]["status"] in {
        "ready_for_wall_graph_review",
        "needs_wall_graph_review",
    }
