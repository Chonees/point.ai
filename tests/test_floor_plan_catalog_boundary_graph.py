from __future__ import annotations

import json
from pathlib import Path

from backend.floor_plan_catalog.boundary_graph import derive_floor_plan_boundary_graph
from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogCadTrace,
    CatalogPoint,
    CatalogReadiness,
    CatalogRoom,
    FloorPlanCatalogSeed,
)


def test_derive_boundary_graph_creates_nodes_and_boundaries_for_l_shape_seed():
    seed = build_l_shape_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert graph.floor_plan_id == seed.floor_plan_id
    assert len(graph.nodes) >= 4
    assert len(graph.boundaries) >= 4
    assert any(node.node_kind == "corner" for node in graph.nodes)
    assert all(boundary.source_trace_ids for boundary in graph.boundaries)


def test_boundary_graph_reprojects_internal_l_shape_edge_to_room_ownership():
    seed = build_l_shape_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    boundary = next(
        boundary
        for boundary in graph.boundaries
        if boundary.start == CatalogPoint(x=40, y=40) and boundary.end == CatalogPoint(x=40, y=120)
    )

    assert boundary.boundary_kind == "exterior"
    assert len(boundary.owner_room_ids) == 1
    assert boundary.confidence in {"trace_projected", "trace_exact"}


def test_boundary_graph_splits_segments_at_tee_intersection():
    seed = build_tee_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert any(node.node_kind == "tee" for node in graph.nodes)
    assert len([boundary for boundary in graph.boundaries if boundary.orientation == "vertical"]) >= 2


def test_boundary_graph_marks_opening_cuts_on_horizontal_wall():
    seed = build_opening_cut_seed()

    graph = derive_floor_plan_boundary_graph(seed)

    assert any(node.node_kind == "opening_cut" for node in graph.nodes)
    assert any(boundary.opening_ids for boundary in graph.boundaries)


def test_boundary_graph_marks_parallel_shell_trace_as_support_boundary():
    seed = build_double_line_shell_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    support_boundary = next(
        boundary
        for boundary in graph.boundaries
        if boundary.boundary_kind == "support"
    )

    assert len(support_boundary.owner_room_ids) == 1
    assert support_boundary.confidence == "trace_companion"
    assert support_boundary.companion_boundary_id is not None


def test_boundary_graph_groups_exact_duplicate_segments_into_one_family():
    seed = build_duplicate_geometry_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    family_members = [
        boundary
        for boundary in graph.boundaries
        if boundary.boundary_family_id is not None
    ]
    canonical = [boundary for boundary in family_members if boundary.family_role == "canonical"]
    duplicates = [boundary for boundary in family_members if boundary.family_role == "duplicate"]

    assert canonical
    assert duplicates
    assert len({boundary.boundary_family_id for boundary in family_members}) == 1
    assert all(boundary.duplicate_of_boundary_id == canonical[0].boundary_id for boundary in duplicates)


def test_boundary_graph_picks_the_best_boundary_as_family_canonical_member():
    seed = build_duplicate_geometry_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    canonical = next(boundary for boundary in graph.boundaries if boundary.family_role == "canonical")

    assert canonical.boundary_kind in {"shared", "exterior", "support"}
    assert canonical.duplicate_of_boundary_id is None


def test_seminole_boundary_graph_produces_shared_boundaries_without_bbox_inference():
    seed = load_seminole_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    shared = [boundary for boundary in graph.boundaries if boundary.boundary_kind == "shared"]

    assert shared
    assert all(
        boundary.confidence in {"trace_exact", "trace_merged", "trace_partitioned", "trace_projected"}
        for boundary in shared
    )
    assert all("bbox_inferred" not in boundary.issues for boundary in shared)
    assert all(len(boundary.owner_room_ids) == 2 for boundary in shared)


def test_seminole_boundary_graph_reduces_unknown_boundary_count():
    seed = load_seminole_seed()

    graph = derive_floor_plan_boundary_graph(seed)
    unknown = [boundary for boundary in graph.boundaries if boundary.boundary_kind == "unknown"]
    support = [boundary for boundary in graph.boundaries if boundary.boundary_kind == "support"]
    duplicates = [boundary for boundary in graph.boundaries if boundary.family_role == "duplicate"]

    assert support
    assert duplicates
    assert len(unknown) < 286


def build_l_shape_seed() -> FloorPlanCatalogSeed:
    room_polygon = [
        CatalogPoint(x=0, y=0),
        CatalogPoint(x=120, y=0),
        CatalogPoint(x=120, y=40),
        CatalogPoint(x=40, y=40),
        CatalogPoint(x=40, y=120),
        CatalogPoint(x=0, y=120),
    ]
    cad_traces = [
        build_trace("wall-1", (0, 0), (120, 0)),
        build_trace("wall-2", (120, 0), (120, 40)),
        build_trace("wall-3", (120, 40), (40, 40)),
        build_trace("wall-4", (40, 40), (40, 120)),
        build_trace("wall-5", (40, 120), (0, 120)),
        build_trace("wall-6", (0, 120), (0, 0)),
    ]
    room = CatalogRoom(
        name="LIVING ROOM",
        polygon=room_polygon,
        bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=120, width=120, height=120),
        centroid=CatalogPoint(x=50, y=50),
        width=120,
        height=120,
        area=11200,
        measurement_source="room_region",
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="l-shape-seed",
        name="L SHAPE",
        source_path="synthetic/l-shape.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=120, width=120, height=120),
        rooms=[room],
        cad_traces=cad_traces,
        source_layers=["WALLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def build_tee_seed() -> FloorPlanCatalogSeed:
    room = CatalogRoom(
        name="HALL",
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
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="tee-seed",
        name="TEE",
        source_path="synthetic/tee.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=100, y2=100, width=100, height=100),
        rooms=[room],
        cad_traces=[
            build_trace("wall-h", (0, 50), (100, 50)),
            build_trace("wall-v", (50, 0), (50, 100)),
        ],
        source_layers=["WALLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def build_opening_cut_seed() -> FloorPlanCatalogSeed:
    room = CatalogRoom(
        name="ENTRY",
        polygon=[
            CatalogPoint(x=0, y=0),
            CatalogPoint(x=120, y=0),
            CatalogPoint(x=120, y=40),
            CatalogPoint(x=0, y=40),
        ],
        bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=40, width=120, height=40),
        centroid=CatalogPoint(x=60, y=20),
        width=120,
        height=40,
        area=4800,
        measurement_source="room_region",
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="opening-cut-seed",
        name="OPENING CUT",
        source_path="synthetic/opening-cut.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=40, width=120, height=40),
        rooms=[room],
        cad_traces=[
            build_trace("wall-long", (0, 20), (120, 20)),
            build_trace("door-cut", (48, 20), (72, 20), trace_kind="door"),
        ],
        source_layers=["WALLS", "DOORS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def build_double_line_shell_seed() -> FloorPlanCatalogSeed:
    room = CatalogRoom(
        name="SHELL ROOM",
        polygon=[
            CatalogPoint(x=0, y=0),
            CatalogPoint(x=100, y=0),
            CatalogPoint(x=100, y=60),
            CatalogPoint(x=0, y=60),
        ],
        bbox=CatalogBBox(x1=0, y1=0, x2=100, y2=60, width=100, height=60),
        centroid=CatalogPoint(x=50, y=30),
        width=100,
        height=60,
        area=6000,
        measurement_source="room_region",
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="double-line-shell-seed",
        name="DOUBLE LINE SHELL",
        source_path="synthetic/double-line-shell.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=109, y2=60, width=109, height=60),
        rooms=[room],
        cad_traces=[
            build_trace("wall-left-primary", (0, 0), (0, 60)),
            build_trace("wall-left-shell", (9, 0), (9, 60)),
            build_trace("wall-top", (0, 60), (100, 60)),
            build_trace("wall-right", (100, 0), (100, 60)),
            build_trace("wall-bottom", (0, 0), (100, 0)),
        ],
        source_layers=["WALLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def build_duplicate_geometry_seed() -> FloorPlanCatalogSeed:
    room = CatalogRoom(
        name="DUPLICATE TEST",
        polygon=[
            CatalogPoint(x=0, y=0),
            CatalogPoint(x=120, y=0),
            CatalogPoint(x=120, y=60),
            CatalogPoint(x=0, y=60),
        ],
        bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=60, width=120, height=60),
        centroid=CatalogPoint(x=60, y=30),
        width=120,
        height=60,
        area=7200,
        measurement_source="room_region",
    )
    return FloorPlanCatalogSeed(
        floor_plan_id="duplicate-geometry-seed",
        name="DUPLICATE GEOMETRY",
        source_path="synthetic/duplicate-geometry.dxf",
        canonical_unit="inch",
        footprint_bbox=CatalogBBox(x1=0, y1=0, x2=120, y2=60, width=120, height=60),
        rooms=[room],
        cad_traces=[
            build_trace("wall-bottom-a", (0, 0), (120, 0)),
            build_trace("wall-bottom-b", (0, 0), (120, 0)),
            build_trace("wall-left", (0, 0), (0, 60)),
            build_trace("wall-right", (120, 0), (120, 60)),
            build_trace("wall-top", (0, 60), (120, 60)),
        ],
        source_layers=["WALLS"],
        block_refs=[],
        readiness=CatalogReadiness(status="ready_for_catalog", issues=[]),
    )


def load_seminole_seed() -> FloorPlanCatalogSeed:
    payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    return FloorPlanCatalogSeed.model_validate(payload)


def build_trace(
    trace_id: str,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    trace_kind: str = "wall",
    layer: str | None = None,
) -> CatalogCadTrace:
    x1, y1 = start
    x2, y2 = end
    return CatalogCadTrace(
        trace_id=trace_id,
        trace_kind=trace_kind,
        type="line",
        layer=layer or ("WALLS" if trace_kind == "wall" else trace_kind.upper()),
        start=CatalogPoint(x=x1, y=y1),
        end=CatalogPoint(x=x2, y=y2),
        bbox=CatalogBBox(
            x1=min(x1, x2),
            y1=min(y1, y2),
            x2=max(x1, x2),
            y2=max(y1, y2),
            width=abs(x2 - x1),
            height=abs(y2 - y1),
        ),
    )
