from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..evaluation.validation import evaluate_episode, evaluate_pair
from ..recording.recorder import write_json
from ..runtime.session import PairSession
from .batch import expand_batch, run_batch
from .config import PROJECT_ROOT, load_pair_config, read_yaml
from .pairing import run_pair
from .registry import get_scenario


def main(argv=None):
    parser = argparse.ArgumentParser(description="Schema-v2 paired risk/counterfactual collection")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--catalog", default=str(PROJECT_ROOT/"configs/catalog.yaml"))
    for name in ("validate", "inspect-site", "run-pair"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
        if name == "inspect-site":
            command.add_argument("--output", help="Write the validated frozen site to a new JSON file")
    batch = commands.add_parser("run-batch")
    batch.add_argument("--config", required=True)
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--max-new-attempts",type=int,help="Stop cleanly after this many new pair attempts; resume with the same batch")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("path")
    args = parser.parse_args(argv)
    if args.command == "catalog":
        result = read_yaml(args.catalog)
    elif args.command == "validate":
        config = load_pair_config(args.config)
        result = {"valid": True, "pair_id": config.pair_id, "config": config.data}
    elif args.command == "inspect-site":
        config = load_pair_config(args.config)
        with PairSession(config.data) as session:
            layout = get_scenario(config.data["scenario"]["scenario_id"]).plan(session.world, config.data)
        result = {"status": "geometry_validated", "layout": layout}
        if args.output:
            destination = Path(args.output)
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_json(destination, result)
    elif args.command == "run-pair":
        path, result = run_pair(load_pair_config(args.config))
        result = {"output": str(path), **result}
    elif args.command == "run-batch":
        if args.dry_run:
            batch_config, source, samples = expand_batch(args.config)
            for sample in samples:
                from .batch import nested_overrides
                load_pair_config(source, nested_overrides(sample))
            result = {"valid": True, "batch_id": batch_config["batch_id"], "pair_count": len(samples), "samples": samples,
                      "baseline_runs": batch_config["baseline_runs"]}
        else:
            path, result = run_batch(args.config,max_new_attempts=args.max_new_attempts)
            result = {"output": str(path), **result}
    else:
        path = Path(args.path)
        if (path/"pair.json").exists():
            result = evaluate_pair(path)
        elif (path/"episode.json").exists():
            result = evaluate_episode(path)
        elif (path/"manifest.json").exists():
            from .batch import evaluate_repeats
            manifest = json.loads((path/"manifest.json").read_text(encoding="utf-8"))
            slots = manifest["samples"]
            reports = [evaluate_pair(s["selected"]) if s["selected"] else {"passed": False} for s in slots]
            result = {"passed": all(r["passed"] for r in reports), "pairs": reports}
            baseline_slots = [s for s in slots if s.get("selected") and s["selected"] == manifest.get("baseline_selected")]
            if baseline_slots:
                baseline = baseline_slots[0]["selected"]
                common = json.loads((Path(baseline)/"pair.json").read_text(encoding="utf-8"))["common_config"]
                good_repeats = [p for p in manifest["baseline_repeats"] if evaluate_pair(p)["passed"]]
                repeatability = evaluate_repeats([baseline, *good_repeats], common["acceptance"]["repeat_event_tolerance_seconds"])
            else:
                repeatability = {"passed": False, "reason": "no_selected_baseline"}
            result["repeatability"] = repeatability
            result["passed"] = result["passed"] and repeatability["passed"]
        else:
            raise ValueError("Expected a v2 episode, pair attempt or batch directory")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1
