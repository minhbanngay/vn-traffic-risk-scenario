from __future__ import annotations

import argparse
import json
import sys

from .carla_runtime import CarlaUnavailableError
from .config import ConfigError, load_config
from .scenario import run_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic VN-Traffic Risk CARLA scenario."
    )
    parser.add_argument("--config", required=True, help="Path to scenario YAML")
    parser.add_argument(
        "--variant",
        choices=("safe", "risk", "collision"),
        help="Override scenario.variant from YAML",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the resolved configuration without connecting to CARLA",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config, args.variant)
        if args.dry_run:
            print(json.dumps(config.data, indent=2, ensure_ascii=False))
            return 0
        output_dir, summary = run_scenario(config)
        print(f"Episode saved to: {output_dir}")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except (ConfigError, CarlaUnavailableError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

