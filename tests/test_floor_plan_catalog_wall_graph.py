import json
from pathlib import Path

from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
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
        source_layers=["WALLS", "ROOM LBLS", "DOORS"],
        block_refs=["TOILET1"],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def test_derive_floor_plan_wall_graph_creates_shared_and_exterior_boundaries():
    topology = derive_floor_plan_topology(build_seed())

    wall_graph = derive_floor_plan_wall_graph(topology)
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

    hall_exterior = next(
        wall
        for wall in walls
        if wall.is_exterior and wall.room_ids == [hall.room_id] and wall.orientation == "vertical"
    )
    assert hall_exterior.start == CatalogPoint(x=240, y=300)
    assert hall_exterior.end == CatalogPoint(x=240, y=500)


def test_derive_floor_plan_wall_graph_falls_back_to_bbox_inference_when_polygons_do_not_touch():
    seed = build_seed().model_copy(deep=True)
    seed.rooms[0].polygon[0] = CatalogPoint(x=0, y=500.99)
    seed.rooms[0].polygon[1] = CatalogPoint(x=160, y=500.99)
    seed.rooms[0].bbox = CatalogBBox(x1=0, y1=500.99, x2=160, y2=792, width=160, height=291.01)

    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology)

    kitchen = next(room for room in topology.rooms if room.name == "KITCHEN")
    bedroom = next(room for room in topology.rooms if room.name == "BEDROOM 2")
    inferred_wall = next(
        wall
        for wall in wall_graph.walls
        if set(wall.room_ids) == {kitchen.room_id, bedroom.room_id}
    )

    assert inferred_wall.orientation == "horizontal"
    assert inferred_wall.start == CatalogPoint(x=0, y=500.495)
    assert inferred_wall.end == CatalogPoint(x=160, y=500.495)
    assert "inferred_from_bbox" in inferred_wall.issues
    assert wall_graph.wall_graph_readiness.status == "needs_wall_graph_review"
    assert "inferred_from_bbox" in wall_graph.wall_graph_issues


def test_derive_floor_plan_wall_graph_deduplicates_shared_boundaries():
    topology = derive_floor_plan_topology(build_seed())

    wall_graph = derive_floor_plan_wall_graph(topology)
    shared_pairs = [tuple(sorted(wall.room_ids)) for wall in wall_graph.walls if not wall.is_exterior]

    assert len(shared_pairs) == len(set(shared_pairs))


def test_derive_floor_plan_wall_graph_handles_real_seminole_seed():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)

    wall_graph = derive_floor_plan_wall_graph(topology)

    assert wall_graph.floor_plan_id == "seminole-2000"
    assert wall_graph.walls
    assert any(len(wall.room_ids) == 2 for wall in wall_graph.walls)
    assert any(wall.is_exterior for wall in wall_graph.walls)
