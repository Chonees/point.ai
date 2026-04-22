from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.floor_plan_catalog.curator import curate_floor_plan_seed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--floor-plan-id")
    parser.add_argument("--name")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    seed = curate_floor_plan_seed(
        Path(args.source),
        floor_plan_id=args.floor_plan_id,
        name=args.name,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(seed.model_dump_json(indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
