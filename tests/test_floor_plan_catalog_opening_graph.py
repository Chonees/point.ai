from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogCadTrace,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
    FloorPlanCatalogSeed,
)
from backend.floor_plan_catalog.opening_graph import derive_floor_plan_opening_graph
from backend.floor_plan_catalog.topology import derive_floor_plan_topology
from backend.floor_plan_catalog.wall_graph import derive_floor_plan_wall_graph


def build_seed_with_hostable_openings() -> FloorPlanCatalogSeed:
    return FloorPlanCatalogSeed(
        floor_plan_id="opening-hosting",
        name="OPENING HOSTING",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/OPENING-HOSTING.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=220, y2=120, width=220, height=120),
        rooms=[
            CatalogRoom(
                name="ROOM A",
                polygon=[
                    CatalogPoint(x=0, y=0),
                    CatalogPoint(x=100, y=0),
                    CatalogPoint(x=100, y=100),
                    CatalogPoint(x=0, y=100),
                ],
                bbox=CatalogBBox(x1=0, y1=0, x2=100, y2=100, width=100, height=100),
                centroid=CatalogPoint(x=50, y=50),
                width=100,
                height=100,
                area=10000,
                measurement_source="room_region",
            ),
            CatalogRoom(
                name="ROOM B",
                polygon=[
                    CatalogPoint(x=100, y=0),
                    CatalogPoint(x=200, y=0),
                    CatalogPoint(x=200, y=100),
                    CatalogPoint(x=100, y=100),
                ],
                bbox=CatalogBBox(x1=100, y1=0, x2=200, y2=100, width=100, height=100),
                centroid=CatalogPoint(x=150, y=50),
                width=100,
                height=100,
                area=10000,
                measurement_source="room_region",
            ),
        ],
        cad_traces=[
            CatalogCadTrace(
                trace_id="shared-wall",
                trace_kind="wall",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=100, y=0),
                end=CatalogPoint(x=100, y=100),
                bbox=CatalogBBox(x1=100, y1=0, x2=100, y2=100, width=0, height=100),
            ),
            CatalogCadTrace(
                trace_id="left-exterior",
                trace_kind="wall",
                type="line",
                layer="WALLS",
                start=CatalogPoint(x=0, y=0),
                end=CatalogPoint(x=0, y=100),
                bbox=CatalogBBox(x1=0, y1=0, x2=0, y2=100, width=0, height=100),
            ),
            CatalogCadTrace(
                trace_id="door-shared",
                trace_kind="door",
                type="line",
                layer="DOORS",
                start=CatalogPoint(x=100, y=40),
                end=CatalogPoint(x=100, y=60),
                bbox=CatalogBBox(x1=100, y1=40, x2=100, y2=60, width=0, height=20),
            ),
            CatalogCadTrace(
                trace_id="window-left",
                trace_kind="window",
                type="line",
                layer="WINS",
                start=CatalogPoint(x=0, y=10),
                end=CatalogPoint(x=0, y=30),
                bbox=CatalogBBox(x1=0, y1=10, x2=0, y2=30, width=0, height=20),
            ),
        ],
        source_layers=["WALLS", "DOORS", "WINS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def test_derive_floor_plan_opening_graph_hosts_door_and_window_traces():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)

    assert opening_graph.openings
    assert opening_graph.opening_graph_readiness.status == "ready_for_opening_review"

    door = next(opening for opening in opening_graph.openings if opening.opening_kind == "door")
    window = next(opening for opening in opening_graph.openings if opening.opening_kind == "window")

    assert door.host_wall_id is not None
    assert len(door.owner_room_ids) == 2
    assert len(door.connected_room_ids) == 2
    assert door.confidence == "hosted"

    assert window.host_wall_id is not None
    assert len(window.owner_room_ids) == 1
    assert window.connected_room_ids == []
    assert window.confidence == "hosted"
