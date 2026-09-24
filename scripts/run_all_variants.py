from __future__ import annotations

import argparse

from vn_traffic_risk.config import load_config
from vn_traffic_risk.scenario import run_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe/risk/collision variants")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    for variant in ("safe", "risk", "collision"):
        config = load_config(args.config, variant)
        output_dir, summary = run_scenario(config)
        print(
            f"{variant}: {output_dir} | "
            f"risk intervals={summary['risk_intervals']} | "
            f"collisions={len(summary['collision_events'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

