from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
import sys
from pathlib import Path

from ..evaluation.validation import evaluate_pair
from ..recording.recorder import write_json
from ..recording.report import write_review
from ..runtime.server import server_scope
from .config import PairConfig, fingerprint, implementation_fingerprint, runtime_environment


def allocate_attempt(parent):
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 1000000):
        path = parent/f"A{index:06d}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise RuntimeError("Attempt namespace exhausted")


def run_pair(config: PairConfig, on_allocated=None):
    identity = {"schema_version": 2, "scenario_id": config.data["scenario"]["scenario_id"], "pair_id": config.pair_id}
    directory = allocate_attempt(config.output_root/identity["scenario_id"]/config.pair_id)
    identity["attempt_id"] = directory.name
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.root, capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        revision = "unavailable"
    environment = runtime_environment()
    manifest = {**identity, "status": "planning", "created_utc": datetime.now(timezone.utc).isoformat(),
                "runtime_environment":environment,"runtime_fingerprint":fingerprint(environment),
                "source_revision": revision, "source_config": str(config.source), "common_config": config.data,
                "implementation_fingerprint": implementation_fingerprint(),
                "config_fingerprint": fingerprint(config.data), "branches": {}, "layout_fingerprint": None}
    write_json(directory/"pair.json", manifest)
    try:
        if on_allocated is not None:
            on_allocated(directory)
        planner_payload = directory/"planner.json"
        write_json(planner_payload, {"config": config.data, "destination": str(directory/"layout.json")})
        with server_scope({**config.data["carla"],"telemetry_path":str(directory/"server_planner.telemetry.jsonl")}):
            with (directory/"planner.stderr.log").open("x", encoding="utf-8") as error_stream:
                process = subprocess.run([sys.executable, "-m", "vn_traffic_risk.core.worker", "--plan", str(planner_payload)], cwd=config.root, check=False, stderr=error_stream, timeout=config.data["carla"].get("worker_timeout_seconds",450))
        if process.returncode or not (directory/"layout.json").exists():
            raise RuntimeError(f"Planning worker failed with exit code {process.returncode}")
        layout = json.loads((directory/"layout.json").read_text(encoding="utf-8"))
        manifest.update(status="running", layout_fingerprint=fingerprint(layout))
        write_json(directory/"pair.json", manifest)
        if implementation_fingerprint() != manifest["implementation_fingerprint"]:
            raise RuntimeError("Implementation changed during pair planning; start a new attempt")
        for branch in ("R", "CF"):
            if implementation_fingerprint() != manifest["implementation_fingerprint"]:
                raise RuntimeError("Implementation changed during pair execution")
            payload = directory/f"worker_{branch}.json"
            write_json(payload,{"config":config.branch(branch),"layout":layout,"branch":branch,
                                "directory":str(directory/branch),"identity":identity})
            print(f"{config.pair_id}/{directory.name}/{branch}",flush=True)
            # Fresh owned engine for each worker: no native episode subscription
            # is handed across SDK processes. Both branches still replay one layout.
            with server_scope({**config.data["carla"],"telemetry_path":str(directory/f"server_{branch}.telemetry.jsonl")}):
                with (directory/f"worker_{branch}.stderr.log").open("x",encoding="utf-8") as error_stream:
                    process = subprocess.run([sys.executable,"-m","vn_traffic_risk.core.worker",str(payload)],cwd=config.root,check=False,stderr=error_stream,timeout=config.data["carla"].get("worker_timeout_seconds",450))
            episode_path = directory/branch/"episode.json"
            if process.returncode or not episode_path.exists() or json.loads(episode_path.read_text(encoding="utf-8")).get("status") == "running":
                failure = {**identity, "branch": branch, "status": "failed", "error": f"worker_exit_code={process.returncode}", "frame_count": 0}
                if episode_path.exists():
                    failure = {**json.loads(episode_path.read_text(encoding="utf-8")), **failure}
                (directory/branch).mkdir(exist_ok=True)
                raw = directory/branch/"frames.raw.jsonl"
                if raw.exists():
                    failure["recoverable_raw_lines"] = sum(1 for _ in raw.open(encoding="utf-8"))
                write_json(episode_path, failure)
            summary = json.loads(episode_path.read_text(encoding="utf-8"))
            manifest["branches"][branch] = summary["status"]
            write_json(directory/"pair.json", manifest)
        if process.returncode:
            manifest["worker_exit_code"] = process.returncode
        report = evaluate_pair(directory)
        write_review(directory)
        states = list(manifest["branches"].values())
        manifest["status"] = ("passed" if report["passed"] else "failed" if "failed" in states
                              else "incomplete" if any(s != "complete" for s in states) else "rejected")
        write_json(directory/"pair.json", manifest)
        return directory, report
    except BaseException as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(directory/"pair.json", manifest)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        report = {"passed": False, "failures": [manifest["error"]]}
        write_json(directory/"validation.json", report)
        return directory, report
