from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
    FloorPlanCatalogSeed,
)
from backend.floor_plan_catalog.topology import derive_floor_plan_topology


def build_seed() -> FloorPlanCatalogSeed:
    return FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=468, y2=792, width=468, height=792),
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


def test_derive_floor_plan_topology_reports_ready_status_for_clean_seed():
    topology = derive_floor_plan_topology(build_seed())

    assert topology.topology_readiness.status == "ready_for_topology_review"
    assert topology.topology_readiness.issues == []
    assert topology.topology_issues == []


def test_derive_floor_plan_topology_keeps_adjacency_symmetric():
    topology = derive_floor_plan_topology(build_seed())

    room_by_id = {room.room_id: room for room in topology.rooms}

    for room in topology.rooms:
        for adjacent_room_id in room.adjacent_room_ids:
            assert room.room_id in room_by_id[adjacent_room_id].adjacent_room_ids


def test_derive_floor_plan_topology_marks_unknown_category_and_isolation_issue():
    seed = build_seed().model_copy(deep=True)
    seed.rooms = [seed.rooms[0].model_copy(deep=True)]
    seed.rooms[0].name = "SPACE X"

    topology = derive_floor_plan_topology(seed)
    room = topology.rooms[0]

    assert room.category == "unknown"
    assert "missing_category" in room.issues
    assert "isolated_room" in room.issues
    assert topology.topology_readiness.status == "needs_topology_review"
    assert topology.topology_readiness.issues == ["isolated_room", "missing_category"]
    assert topology.topology_issues == ["isolated_room", "missing_category"]


def test_derive_floor_plan_topology_is_deterministic_between_runs():
    first = derive_floor_plan_topology(build_seed()).model_dump()
    second = derive_floor_plan_topology(build_seed()).model_dump()

    assert first == second


def test_derive_floor_plan_topology_keeps_room_id_stable_when_centroid_moves():
    seed_a = build_seed().model_copy(deep=True)
    seed_b = build_seed().model_copy(deep=True)

    seed_a.rooms[0].centroid = CatalogPoint(x=80.2, y=646.2)
    seed_b.rooms[0].centroid = CatalogPoint(x=80.8, y=646.8)

    topology_a = derive_floor_plan_topology(seed_a)
    topology_b = derive_floor_plan_topology(seed_b)

    assert topology_a.rooms[0].room_id == topology_b.rooms[0].room_id


def test_derive_floor_plan_topology_avoids_room_id_collision_for_similar_rooms():
    seed = build_seed().model_copy(deep=True)
    seed.rooms[0].name = "OFFICE"
    seed.rooms[0].centroid = CatalogPoint(x=120.2, y=646.2)
    seed.rooms[1] = seed.rooms[0].model_copy(deep=True)
    seed.rooms[1].bbox = CatalogBBox(x1=0, y1=320, x2=180, y2=520, width=180, height=200)
    seed.rooms[1].polygon = [
        CatalogPoint(x=0, y=320),
        CatalogPoint(x=180, y=320),
        CatalogPoint(x=180, y=520),
        CatalogPoint(x=0, y=520),
    ]
    seed.rooms[1].centroid = CatalogPoint(x=90.2, y=420.2)

    topology = derive_floor_plan_topology(seed)
    room_ids = [room.room_id for room in topology.rooms]

    assert len(room_ids) == len(set(room_ids))


def test_derive_floor_plan_topology_marks_suspicious_polygon():
    seed = build_seed().model_copy(deep=True)
    seed.rooms = [seed.rooms[0].model_copy(deep=True)]
    seed.rooms[0].polygon = [
        CatalogPoint(x=0, y=500),
        CatalogPoint(x=160, y=500),
        CatalogPoint(x=160, y=792),
    ]
    seed.rooms[0].area = 0

    topology = derive_floor_plan_topology(seed)
    room = topology.rooms[0]

    assert "suspicious_polygon" in room.issues
    assert topology.topology_readiness.status == "needs_topology_review"
    assert "suspicious_polygon" in topology.topology_issues
