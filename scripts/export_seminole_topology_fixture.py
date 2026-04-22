from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed
from backend.floor_plan_catalog.boundary_graph import derive_floor_plan_boundary_graph
from backend.floor_plan_catalog.opening_graph import derive_floor_plan_opening_graph
from backend.floor_plan_catalog.topology import derive_floor_plan_topology, strengthen_floor_plan_topology
from backend.floor_plan_catalog.wall_graph import derive_floor_plan_wall_graph


def build_inspector_payload(seed: FloorPlanCatalogSeed) -> dict:
    boundary_graph = derive_floor_plan_boundary_graph(seed)
    topology = derive_floor_plan_topology(seed)
    wall_graph = derive_floor_plan_wall_graph(topology, seed.cad_traces)
    opening_graph = derive_floor_plan_opening_graph(topology, wall_graph, seed.cad_traces)
    topology = strengthen_floor_plan_topology(topology, wall_graph, seed.cad_traces, opening_graph)
    payload = topology.model_dump()
    payload["cad_traces"] = [trace.model_dump() for trace in seed.cad_traces]
    payload["boundary_nodes"] = [node.model_dump() for node in boundary_graph.nodes]
    payload["boundaries"] = [boundary.model_dump() for boundary in boundary_graph.boundaries]
    payload["boundary_graph_readiness"] = boundary_graph.boundary_graph_readiness.model_dump()
    payload["boundary_graph_issues"] = boundary_graph.boundary_graph_issues
    payload["walls"] = [wall.model_dump() for wall in wall_graph.walls]
    payload["wall_graph_readiness"] = wall_graph.wall_graph_readiness.model_dump()
    payload["wall_graph_issues"] = wall_graph.wall_graph_issues
    payload["openings"] = [opening.model_dump() for opening in opening_graph.openings]
    payload["opening_graph_readiness"] = opening_graph.opening_graph_readiness.model_dump()
    payload["opening_graph_issues"] = opening_graph.opening_graph_issues
    return payload


def export_topology_fixture(seed_path: Path, output_path: Path):
    seed_payload = json.loads(seed_path.read_text(encoding="utf-8"))
    seed = FloorPlanCatalogSeed.model_validate(seed_payload)
    payload = build_inspector_payload(seed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed_json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    export_topology_fixture(Path(args.seed_json), output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
