import json
from collections import Counter
from pathlib import Path

from backend.floor_plan_catalog.boundary_graph import derive_floor_plan_boundary_graph
from backend.floor_plan_catalog.contracts import (
    CatalogBBox,
    CatalogCadTrace,
    CatalogPoint,
    CatalogRoom,
    FloorPlanCatalogSeed,
)
from backend.floor_plan_catalog.opening_graph import derive_floor_plan_opening_graph
from backend.floor_plan_catalog.topology import derive_floor_plan_topology, strengthen_floor_plan_topology
from backend.floor_plan_catalog.wall_graph import derive_floor_plan_wall_graph
from backend.floor_plan_catalog.mutability import derive_floor_plan_mutability


def _point(x: float, y: float) -> CatalogPoint:
    return CatalogPoint(x=x, y=y)


def _bbox(x1: float, y1: float, x2: float, y2: float) -> CatalogBBox:
    return CatalogBBox(
        x1=min(x1, x2),
        y1=min(y1, y2),
        x2=max(x1, x2),
        y2=max(y1, y2),
        width=abs(x2 - x1),
        height=abs(y2 - y1),
    )


def _room(name: str, x1: float, y1: float, x2: float, y2: float) -> CatalogRoom:
    polygon = [
        _point(x1, y1),
        _point(x2, y1),
        _point(x2, y2),
        _point(x1, y2),
    ]
    return CatalogRoom(
        name=name,
        polygon=polygon,
        bbox=_bbox(x1, y1, x2, y2),
        centroid=_point((x1 + x2) / 2, (y1 + y2) / 2),
        width=abs(x2 - x1),
        height=abs(y2 - y1),
        area=abs((x2 - x1) * (y2 - y1)),
        measurement_source="room_region",
    )


def _wall_trace(trace_id: str, x1: float, y1: float, x2: float, y2: float) -> CatalogCadTrace:
    return CatalogCadTrace(
        trace_id=trace_id,
        trace_kind="wall",
        type="line",
        layer="WALLS",
        start=_point(x1, y1),
        end=_point(x2, y2),
        bbox=_bbox(x1, y1, x2, y2),
    )


def _opening_trace(trace_id: str, trace_kind: str, x1: float, y1: float, x2: float, y2: float) -> CatalogCadTrace:
    layer = "DOORS" if trace_kind == "door" else "WINS"
    return CatalogCadTrace(
        trace_id=trace_id,
        trace_kind=trace_kind,
        type="line",
        layer=layer,
        start=_point(x1, y1),
        end=_point(x2, y2),
        bbox=_bbox(x1, y1, x2, y2),
    )


def _canonical_segment(x1: float, y1: float, x2: float, y2: float) -> tuple[tuple[float, float], tuple[float, float]]:
    return tuple(sorted(((x1, y1), (x2, y2))))  # type: ignore[return-value]


def _seed_from_layout(
    *,
    floor_plan_id: str,
    name: str,
    room_defs: list[tuple[str, float, float, float, float]],
    openings: list[CatalogCadTrace] | None = None,
) -> FloorPlanCatalogSeed:
    rooms = [_room(*room_def) for room_def in room_defs]
    x1 = min(room.bbox.x1 for room in rooms)
    y1 = min(room.bbox.y1 for room in rooms)
    x2 = max(room.bbox.x2 for room in rooms)
    y2 = max(room.bbox.y2 for room in rooms)

    wall_segments: dict[tuple[tuple[float, float], tuple[float, float]], CatalogCadTrace] = {}
    for room in rooms:
        points = room.polygon
        for index in range(len(points)):
            start = points[index]
            end = points[(index + 1) % len(points)]
            key = _canonical_segment(start.x, start.y, end.x, end.y)
            if key not in wall_segments:
                wall_segments[key] = _wall_trace(
                    trace_id=f"wall-{len(wall_segments) + 1}",
                    x1=key[0][0],
                    y1=key[0][1],
                    x2=key[1][0],
                    y2=key[1][1],
                )

    cad_traces = list(wall_segments.values()) + list(openings or [])
    source_layers = sorted({trace.layer for trace in cad_traces})

    return FloorPlanCatalogSeed(
        floor_plan_id=floor_plan_id,
        name=name,
        source_path=f"D:/PointAIData/PLANS/originalFloorPlans/{name}.dxf",
        canonical_unit="inch",
        footprint_bbox=_bbox(x1, y1, x2, y2),
        rooms=rooms,
        cad_traces=cad_traces,
        source_layers=source_layers,
        block_refs=[],
        readiness={"status": "ready_for_catalog", "issues": []},
    )


def _derive_graphs(seed: FloorPlanCatalogSeed):
    topology = derive_floor_plan_topology(seed)
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces, boundary_graph=boundary_graph)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    topology = strengthen_floor_plan_topology(topology, wall_graph, seed.cad_traces, opening_graph)
    return derive_floor_plan_mutability(topology, wall_graph, opening_graph, boundary_graph)


def build_seed_for_room_categories() -> FloorPlanCatalogSeed:
    return _seed_from_layout(
        floor_plan_id="mutability-room-categories",
        name="MUTABILITY ROOM CATEGORIES",
        room_defs=[
            ("KITCHEN", 0, 0, 100, 100),
            ("MASTER BATH", 100, 0, 200, 100),
            ("ENTRY", 200, 0, 280, 100),
            ("LIVING ROOM", 280, 0, 420, 100),
            ("PATIO", 420, 0, 520, 100),
        ],
    )


def build_seed_for_flexible_boundaries() -> FloorPlanCatalogSeed:
    return _seed_from_layout(
        floor_plan_id="mutability-flexible-boundaries",
        name="MUTABILITY FLEXIBLE BOUNDARIES",
        room_defs=[
            ("LIVING ROOM", 0, 0, 100, 100),
            ("DINING", 100, 0, 200, 100),
        ],
        openings=[
            _opening_trace("door-shared", "door", 100, 40, 100, 60),
            _opening_trace("window-left", "window", 0, 20, 0, 40),
        ],
    )


def build_seed_for_code_constraints() -> FloorPlanCatalogSeed:
    return _seed_from_layout(
        floor_plan_id="mutability-code-constraints",
        name="MUTABILITY CODE CONSTRAINTS",
        room_defs=[
            ("ENTRY", 0, 0, 80, 100),
            ("LIVING ROOM", 80, 0, 220, 100),
            ("GARAGE", 0, 100, 120, 220),
            ("BEDROOM 1", 120, 100, 220, 220),
        ],
        openings=[
            _opening_trace("entry-egress-door", "door", 0, 30, 0, 60),
            _opening_trace("bedroom-egress-window", "window", 150, 220, 185, 220),
            _opening_trace("entry-living-door", "door", 80, 40, 80, 65),
        ],
    )


def test_derive_floor_plan_mutability_classifies_room_categories_conservatively():
    seed = build_seed_for_room_categories()

    topology, wall_graph, opening_graph, boundary_graph = _derive_graphs(seed)

    rooms = {room.name: room for room in topology.rooms}

    assert rooms["KITCHEN"].mutability == "protected"
    assert rooms["KITCHEN"].is_wet_zone is True
    assert rooms["MASTER BATH"].mutability == "protected"
    assert rooms["ENTRY"].mutability == "protected"
    assert rooms["LIVING ROOM"].mutability == "flexible"
    assert rooms["PATIO"].mutability == "locked"
    assert "wet_core" in rooms["KITCHEN"].constraint_reasons


def test_derive_floor_plan_mutability_marks_boundaries_and_openings_for_executor_use():
    seed = build_seed_for_flexible_boundaries()

    topology, wall_graph, opening_graph, boundary_graph = _derive_graphs(seed)

    boundaries = {boundary.boundary_id: boundary for boundary in boundary_graph.boundaries}
    walls = {wall.wall_id: wall for wall in wall_graph.walls}
    openings = {opening.opening_id: opening for opening in opening_graph.openings}

    assert any(boundary.mutability == "movable" for boundary in boundaries.values() if boundary.boundary_kind == "exterior")
    assert any(boundary.mutability == "movable_with_rehost" for boundary in boundaries.values() if boundary.opening_ids)
    assert all(boundary.mutability == "derived_only" for boundary in boundaries.values() if boundary.boundary_kind in {"duplicate", "artifact", "support"})
    assert any(wall.mutability in {"movable", "movable_with_rehost"} for wall in walls.values())
    assert any(opening.rehost_required is True for opening in openings.values() if opening.confidence == "hosted")
    assert all(opening.rehostable is False for opening in openings.values() if opening.confidence == "opening_artifact")


def test_derive_floor_plan_mutability_protects_code_informed_boundaries_and_openings():
    seed = build_seed_for_code_constraints()

    topology, wall_graph, opening_graph, boundary_graph = _derive_graphs(seed)

    garage_boundaries = [
        boundary for boundary in boundary_graph.boundaries
        if boundary.boundary_kind in {"shared", "exterior"} and "garage_separation" in boundary.constraint_reasons
    ]
    bedroom_egress_openings = [
        opening for opening in opening_graph.openings
        if "required_egress_opening" in opening.constraint_reasons
    ]
    egress_door_openings = [
        opening for opening in opening_graph.openings
        if "required_egress_door" in opening.constraint_reasons
    ]

    assert garage_boundaries
    assert all(boundary.mutability == "protected" for boundary in garage_boundaries)
    assert bedroom_egress_openings
    assert all(opening.rehostable is False for opening in bedroom_egress_openings)
    assert egress_door_openings
    assert all(opening.rehostable is False for opening in egress_door_openings)


def test_derive_floor_plan_mutability_covers_real_seminole_without_structural_regression():
    seed_payload = json.loads(Path(r"D:\PointAIData\PLANS\catalog\seminole-2000.json").read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)

    topology, wall_graph, opening_graph, boundary_graph = _derive_graphs(seed)

    assert all(room.mutability in {"flexible", "protected", "locked"} for room in topology.rooms)
    assert all(boundary.mutability != "unknown" for boundary in boundary_graph.boundaries if boundary.boundary_kind in {"shared", "exterior", "duplicate", "artifact", "support"})
    assert all(wall.mutability != "unknown" for wall in wall_graph.walls)
    assert all(opening.rehostable is False for opening in opening_graph.openings if opening.confidence == "opening_artifact")
    assert any("required_egress_door" in opening.constraint_reasons for opening in opening_graph.openings)
    assert any("garage_separation" in boundary.constraint_reasons for boundary in boundary_graph.boundaries)

    boundary_kinds = Counter(boundary.boundary_kind for boundary in boundary_graph.boundaries)
    assert boundary_kinds["shared"] == 10
    assert boundary_kinds["exterior"] == 182
    assert boundary_kinds["support"] == 40
    assert boundary_kinds["unknown"] == 14
