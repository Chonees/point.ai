import json
from pathlib import Path

from backend.floor_plan_catalog.boundary_graph import derive_floor_plan_boundary_graph
from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogCadTrace,
    CatalogWallBoundary,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
    FloorPlanCatalogSeed,
    FloorPlanWallGraphV1,
    WallGraphReadiness,
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


def test_derive_floor_plan_opening_graph_prefers_exact_canonical_wall_when_candidates_tie():
    seed = build_seed_with_hostable_openings()
    topology = derive_floor_plan_topology(seed)
    room_a = topology.rooms[0].room_id
    room_b = topology.rooms[1].room_id

    inferred_wall = CatalogWallBoundary(
        wall_id="wall-inferred",
        start=CatalogPoint(x=100, y=0),
        end=CatalogPoint(x=100, y=100),
        orientation="vertical",
        length=100,
        is_exterior=False,
        room_ids=[room_a, room_b],
        boundary_kind="shared",
        owner_room_ids=[room_a, room_b],
        provenance="bbox_inferred",
        confidence="trace_supported",
        trace_support_status="snapped_to_trace",
        trace_support_ids=["shared-wall"],
        trace_support_gap=2.0,
    )
    canonical_wall = inferred_wall.model_copy(
        update={
            "wall_id": "wall-canonical",
            "provenance": "boundary_graph_shared",
            "confidence": "exact",
            "trace_support_status": "exact_trace_supported",
            "trace_support_gap": 0.0,
        }
    )
    wall_graph = FloorPlanWallGraphV1(
        floor_plan_id=topology.floor_plan_id,
        name=topology.name,
        canonical_unit=topology.canonical_unit,
        footprint_bbox=topology.footprint_bbox,
        walls=[inferred_wall, canonical_wall],
        wall_graph_readiness=WallGraphReadiness(status="ready_for_wall_graph_review", issues=[]),
        wall_graph_issues=[],
    )

    opening_graph = derive_floor_plan_opening_graph(
        topology,
        wall_graph,
        [trace for trace in seed.cad_traces if trace.trace_id == "door-shared"],
    )

    door = next(opening for opening in opening_graph.openings if opening.opening_kind == "door")

    assert door.host_wall_id == "wall-canonical"
    assert door.confidence == "hosted"


def test_derive_floor_plan_opening_graph_groups_fragmented_door_traces_before_hosting():
    seed = build_seed_with_hostable_openings()
    seed = seed.model_copy(
        update={
            "cad_traces": seed.cad_traces
            + [
                CatalogCadTrace(
                    trace_id="door-swing",
                    trace_kind="door",
                    type="line",
                    layer="DOORS",
                    start=CatalogPoint(x=120, y=60),
                    end=CatalogPoint(x=140, y=60),
                    bbox=CatalogBBox(x1=120, y1=60, x2=140, y2=60, width=20, height=0),
                )
            ]
        }
    )
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)

    opening_graph = derive_floor_plan_opening_graph(
        topology,
        wall_graph,
        seed.cad_traces,
        grouping_tolerance=150.0,
    )

    door_openings = [opening for opening in opening_graph.openings if opening.opening_kind == "door"]

    assert len(door_openings) == 1
    assert door_openings[0].confidence == "hosted"
    assert set(door_openings[0].trace_ids) == {"door-shared", "door-swing"}


def test_derive_floor_plan_opening_graph_reduces_real_seminole_unhosted_openings():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)

    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    unhosted = [opening for opening in opening_graph.openings if opening.confidence == "unhosted"]
    hosted = [opening for opening in opening_graph.openings if opening.confidence == "hosted"]

    assert len(unhosted) < 111
    assert len(hosted) > 51
