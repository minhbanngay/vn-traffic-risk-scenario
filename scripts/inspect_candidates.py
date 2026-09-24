from __future__ import annotations

import argparse
import json

from vn_traffic_risk.carla_runtime import WorldManager
from vn_traffic_risk.config import load_config
from vn_traffic_risk.placement import list_automatic_cut_in_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="List automatic cut-in locations")
    parser.add_argument("--config", required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    config = load_config(args.config)
    manager = WorldManager(config.data["carla"])
    try:
        world = manager.connect()
        candidates = list_automatic_cut_in_candidates(
            world.get_map(),
            config.data["placement"],
        )
        print(json.dumps(candidates[: args.limit], indent=2))
        print(f"Total candidates: {len(candidates)}")
        return 0
    finally:
        manager.restore()


if __name__ == "__main__":
    raise SystemExit(main())

